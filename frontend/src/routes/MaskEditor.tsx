import { useEffect, useMemo, useRef, useState } from "react";
import Konva from "konva";
import { Stage, Layer, Image as KImage, Line, Rect } from "react-konva";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Eraser, Paintbrush, RotateCcw, RotateCw, Trash2, Save, RefreshCw } from "lucide-react";
import { api, fileUrl } from "../lib/api";
import { useElementSize } from "../hooks/useElementSize";

/** Layered mask editor backed by react-konva.
 *
 *  - Strokes are stored in *native* image coordinates (mask must match the
 *    captured frame size for the upstream allsky_maskimage module to accept it).
 *  - The Stage is rendered at display size with a uniform scale; pointer
 *    coordinates are converted via `getRelativePointerPosition`, which already
 *    accounts for the stage scale.
 *  - Undo/redo is a strokes-history pointer — cheap and bounded by user actions
 *    rather than per-pixel data.
 *  - Save extracts the mask layer at native resolution via `toCanvas`, composites
 *    it onto a black background, and PUTs the resulting PNG. The backend
 *    re-saves it as single-channel L mode and atomically replaces the file. */

interface Stroke {
  tool: "draw" | "erase";
  size: number;
  points: number[]; // [x1,y1,x2,y2,...] in native coords
}

export default function MaskEditor() {
  const qc = useQueryClient();
  const { data, refetch } = useQuery({ queryKey: ["masks"], queryFn: api.masks });
  const dims = data?.frame_dimensions;

  const [containerRef, containerSize] = useElementSize<HTMLDivElement>();
  const [baseImage, setBaseImage] = useState<HTMLImageElement | null>(null);
  const [imageVersion, setImageVersion] = useState(0); // forces refetch on click

  // Tool state.
  const [tool, setTool] = useState<"draw" | "erase">("draw");
  const [brush, setBrush] = useState(60);
  const opacity = 0.7; // fixed display opacity for visibility while editing
  const [name, setName] = useState("mask.png");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // Stroke history with undo/redo pointer.
  const [history, setHistory] = useState<Stroke[]>([]);
  const [historyStep, setHistoryStep] = useState(0); // visible = history.slice(0, historyStep)
  const visible = useMemo(() => history.slice(0, historyStep), [history, historyStep]);

  // Konva refs for export.
  const stageRef = useRef<Konva.Stage | null>(null);
  const maskLayerRef = useRef<Konva.Layer | null>(null);
  const drawingRef = useRef(false);

  // Load the latest frame as a plain HTMLImageElement (Konva accepts it directly).
  useEffect(() => {
    const img = new window.Image();
    img.crossOrigin = "anonymous";
    img.onload = () => setBaseImage(img);
    img.onerror = () => setBaseImage(null);
    img.src = `${fileUrl.liveLatest()}?_v=${imageVersion}`;
  }, [imageVersion]);

  // Native dimensions: prefer the live frame dims; fall back to image natural size.
  const nativeW = dims?.width ?? baseImage?.naturalWidth ?? 0;
  const nativeH = dims?.height ?? baseImage?.naturalHeight ?? 0;

  // Compute responsive scale: fit to container width, preserve aspect ratio.
  const scale = useMemo(() => {
    if (!nativeW || !containerSize.width) return 1;
    return Math.min(1, containerSize.width / nativeW);
  }, [containerSize.width, nativeW]);

  const stageW = nativeW * scale;
  const stageH = nativeH * scale;

  function startStroke(e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
    const stage = e.target.getStage();
    if (!stage) return;
    const pos = stage.getRelativePointerPosition();
    if (!pos) return;
    drawingRef.current = true;
    const next: Stroke = { tool, size: brush, points: [pos.x, pos.y] };
    // Drop forward history when branching from an undone state.
    setHistory((h) => [...h.slice(0, historyStep), next]);
    setHistoryStep((s) => s + 1);
  }

  function extendStroke(e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
    if (!drawingRef.current) return;
    const stage = e.target.getStage();
    if (!stage) return;
    const pos = stage.getRelativePointerPosition();
    if (!pos) return;
    setHistory((h) => {
      const idx = historyStep - 1;
      if (idx < 0) return h;
      const next = h.slice();
      next[idx] = { ...next[idx], points: [...next[idx].points, pos.x, pos.y] };
      return next;
    });
  }

  function endStroke() {
    drawingRef.current = false;
  }

  function undo() {
    setHistoryStep((s) => Math.max(0, s - 1));
  }
  function redo() {
    setHistoryStep((s) => Math.min(history.length, s + 1));
  }
  function clear() {
    setHistory([]);
    setHistoryStep(0);
  }

  async function save() {
    if (!nativeW || !nativeH) return;
    setBusy(true);
    setMsg(null);
    try {
      // Render the mask at native resolution by drawing strokes onto an
      // offscreen canvas (bypassing Konva's display scaling entirely).
      const out = document.createElement("canvas");
      out.width = nativeW;
      out.height = nativeH;
      const ctx = out.getContext("2d")!;

      // Start with black background (unmasked = black).
      ctx.fillStyle = "black";
      ctx.fillRect(0, 0, nativeW, nativeH);

      // Draw loaded existing mask first if present.
      if (loadedMaskImage) {
        ctx.drawImage(loadedMaskImage, 0, 0, nativeW, nativeH);
      }

      // Replay all visible strokes at native coordinates.
      for (const stroke of visible) {
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.lineWidth = stroke.size;

        if (stroke.tool === "erase") {
          ctx.globalCompositeOperation = "destination-out";
          ctx.strokeStyle = "white";
        } else {
          ctx.globalCompositeOperation = "source-over";
          ctx.strokeStyle = "white";
        }

        ctx.beginPath();
        for (let i = 0; i < stroke.points.length; i += 2) {
          const x = stroke.points[i];
          const y = stroke.points[i + 1];
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      const blob: Blob | null = await new Promise((resolve) =>
        out.toBlob((b) => resolve(b), "image/png"),
      );
      if (!blob) throw new Error("canvas encode failed");

      await api.uploadMask(name, blob);
      setMsg(`Saved ${name} (${nativeW}\u00d7${nativeH})`);
      qc.invalidateQueries({ queryKey: ["masks"] });
    } catch (e) {
      setMsg(`Failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  // Load an existing mask into the canvas as a single full-coverage stroke.
  // We don't try to recover the original stroke list — only round-trip the
  // bitmap, which is enough to keep editing it (any new strokes get added on
  // top and the export reproduces a binary mask).
  function loadExistingMask(maskName: string) {
    if (!nativeW || !nativeH) return;
    const img = new window.Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      // Use a hidden offscreen canvas to decode the bitmap, then render as a
      // KImage layer entry that's not editable but stays as the "base" of new
      // strokes. We achieve this by clearing history and inserting a synthetic
      // "image-stroke" — but Konva Lines can't carry images. Simplest path:
      // clear history and rely on the next save being a re-encode after the
      // user paints over it. For loading, we just visually overlay the
      // existing mask via `loadedMaskImage` state.
      setLoadedMaskImage(img);
      clear();
    };
    img.src = `${fileUrl.mask(maskName)}?_v=${Date.now()}`;
  }
  const [loadedMaskImage, setLoadedMaskImage] = useState<HTMLImageElement | null>(null);

  return (
    <div className="flex flex-col gap-4">
      {/* Instructions */}
      <div className="card bg-accent/5 border-accent/20">
        <h2 className="text-lg font-semibold mb-2">Mask Editor</h2>
        <div className="text-sm text-ink-muted space-y-1">
          <p><strong>Paint areas to exclude</strong> from all analysis (meteor detection, focus quality, etc.).</p>
          <p>Painted areas will be <strong>ignored</strong> — no meteor detection, no focus analysis, no exposure calculation in those regions. Use this to block trees, buildings, or horizon obstructions.</p>
          <p>Use <strong>Draw</strong> to paint exclusion zones and <strong>Erase</strong> to remove them. The captured image is still shown in full — only the analysis is masked.</p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="card flex flex-wrap items-center gap-3">
        <div className="flex gap-1">
          <ToolButton
            label="Draw"
            icon={<Paintbrush size={16} />}
            active={tool === "draw"}
            onClick={() => setTool("draw")}
          />
          <ToolButton
            label="Erase"
            icon={<Eraser size={16} />}
            active={tool === "erase"}
            onClick={() => setTool("erase")}
          />
        </div>

        <div className="flex items-center gap-2 text-sm">
          <span className="text-ink-muted">Brush</span>
          <input
            type="range"
            min={4}
            max={300}
            value={brush}
            onChange={(e) => setBrush(parseInt(e.target.value, 10))}
          />
          <span className="font-mono w-10 text-right">{brush}</span>
        </div>


        <div className="flex gap-1">
          <ToolButton
            label="Undo"
            icon={<RotateCcw size={16} />}
            disabled={historyStep === 0}
            onClick={undo}
          />
          <ToolButton
            label="Redo"
            icon={<RotateCw size={16} />}
            disabled={historyStep >= history.length}
            onClick={redo}
          />
          <ToolButton
            label="Clear"
            icon={<Trash2 size={16} />}
            disabled={history.length === 0 && !loadedMaskImage}
            onClick={() => {
              clear();
              setLoadedMaskImage(null);
            }}
          />
          <ToolButton
            label="Refresh"
            icon={<RefreshCw size={16} />}
            onClick={() => setImageVersion((v) => v + 1)}
          />
        </div>

        <div className="flex items-center gap-2 text-sm ml-auto">
          <span className="text-ink-muted">Name</span>
          <input
            className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm font-mono w-44"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button
            disabled={busy || !nativeW}
            onClick={save}
            className="px-3 py-1.5 rounded-lg bg-accent text-bg-base font-medium disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            <Save size={16} />
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
        {msg && <div className="basis-full text-xs text-ink-dim">{msg}</div>}
      </div>

      {/* Canvas */}
      <div className="card">
        {nativeW > 0 ? (
          <div ref={containerRef} className="w-full">
            {containerSize.width > 0 && (
              <Stage
                ref={stageRef}
                width={stageW}
                height={stageH}
                scaleX={scale}
                scaleY={scale}
                onMouseDown={startStroke}
                onMouseMove={extendStroke}
                onMouseUp={endStroke}
                onMouseLeave={endStroke}
                onTouchStart={startStroke}
                onTouchMove={extendStroke}
                onTouchEnd={endStroke}
                style={{ touchAction: "none", cursor: "crosshair", borderRadius: 12 }}
              >
                {/* Base layer: latest sky frame */}
                <Layer listening={false}>
                  {baseImage && (
                    <KImage image={baseImage} width={nativeW} height={nativeH} />
                  )}
                </Layer>

                {/* Mask layer */}
                <Layer ref={maskLayerRef} opacity={opacity}>
                  {/* Existing mask preview, if loaded */}
                  {loadedMaskImage && (
                    <KImage image={loadedMaskImage} width={nativeW} height={nativeH} />
                  )}
                  {/* Strokes */}
                  {visible.map((s, i) => (
                    <Line
                      key={i}
                      points={s.points}
                      stroke="white"
                      strokeWidth={s.size}
                      tension={0.4}
                      lineCap="round"
                      lineJoin="round"
                      globalCompositeOperation={
                        s.tool === "erase" ? "destination-out" : "source-over"
                      }
                    />
                  ))}
                </Layer>

                {/* Subtle border */}
                <Layer listening={false}>
                  <Rect
                    x={0}
                    y={0}
                    width={nativeW}
                    height={nativeH}
                    stroke="#1a2233"
                    strokeWidth={2 / scale}
                  />
                </Layer>
              </Stage>
            )}
          </div>
        ) : (
          <div className="text-ink-dim text-sm">Waiting for a frame from the camera…</div>
        )}
      </div>

      {/* Existing masks */}
      <section className="card">
        <h3 className="text-sm uppercase tracking-wide text-ink-muted mb-2">
          Existing masks
        </h3>
        {data?.masks.length ? (
          <ul className="text-sm divide-y divide-bg-raised">
            {data.masks.map((m) => (
              <li key={m.name} className="py-2 flex items-center gap-3">
                <span className="font-mono">{m.name}</span>
                <span className="text-ink-dim text-xs">
                  {m.width}×{m.height}
                </span>
                <button
                  className="ml-auto text-xs px-2 py-1 rounded-lg border border-bg-raised text-ink-muted"
                  onClick={() => loadExistingMask(m.name)}
                >
                  load
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-ink-dim text-sm">No masks yet.</div>
        )}
      </section>

      <div className="text-xs text-ink-dim">
        Hint: masks are stored as <span className="font-mono">{`{ALLSKY_HOME}/config/overlay/images/<name>.png`}</span>{" "}
        and used by the upstream <span className="font-mono">allsky_maskimage</span>{" "}
        module on every captured frame.
      </div>
    </div>
  );
}

function ToolButton(props: {
  label: string;
  icon: React.ReactNode;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={props.onClick}
      disabled={props.disabled}
      className={`px-2.5 py-1.5 rounded-lg border text-sm flex items-center gap-1.5 ${
        props.active
          ? "bg-bg-raised border-accent text-accent"
          : "border-bg-raised text-ink-muted hover:text-ink"
      } disabled:opacity-40 disabled:cursor-not-allowed`}
      title={props.label}
    >
      {props.icon}
      <span className="hidden sm:inline">{props.label}</span>
    </button>
  );
}
