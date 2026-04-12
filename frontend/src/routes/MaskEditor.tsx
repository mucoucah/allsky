import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fileUrl } from "../lib/api";

/** Minimal in-browser mask editor.
 *
 *  Loads the latest frame, lets the user paint with a brush onto a canvas
 *  exactly the same size, and uploads the result as a single-channel PNG.
 *  No external libs — just the Canvas 2D API. M5 swaps in react-konva for
 *  layers/undo/erase modes, but this is enough to validate the round trip. */
export default function MaskEditor() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["masks"], queryFn: api.masks });
  const dims = data?.frame_dimensions;

  const baseRef = useRef<HTMLImageElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [brush, setBrush] = useState(40);
  const [mode, setMode] = useState<"draw" | "erase">("draw");
  const [name, setName] = useState("mask.png");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // Initialise canvas to match frame dimensions once we know them.
  useEffect(() => {
    if (!dims || !canvasRef.current) return;
    const c = canvasRef.current;
    c.width = dims.width;
    c.height = dims.height;
    const ctx = c.getContext("2d")!;
    ctx.clearRect(0, 0, c.width, c.height);
  }, [dims?.width, dims?.height]);

  function pointerToCanvas(e: React.PointerEvent<HTMLCanvasElement>): [number, number] {
    const c = canvasRef.current!;
    const r = c.getBoundingClientRect();
    return [
      ((e.clientX - r.left) / r.width) * c.width,
      ((e.clientY - r.top) / r.height) * c.height,
    ];
  }

  const dragging = useRef(false);
  const lastPt = useRef<[number, number] | null>(null);

  function paintAt(x: number, y: number) {
    const ctx = canvasRef.current!.getContext("2d")!;
    ctx.globalCompositeOperation = mode === "draw" ? "source-over" : "destination-out";
    ctx.fillStyle = "white";
    ctx.beginPath();
    ctx.arc(x, y, brush / 2, 0, Math.PI * 2);
    ctx.fill();
  }

  async function save() {
    if (!canvasRef.current) return;
    setBusy(true); setMsg(null);
    // Convert RGBA canvas → grayscale L PNG.
    // Easiest path: white where we drew, black elsewhere. The backend
    // re-encodes to L mode anyway, so we just need a binary mask.
    const c = canvasRef.current;
    const out = document.createElement("canvas");
    out.width = c.width; out.height = c.height;
    const octx = out.getContext("2d")!;
    octx.fillStyle = "black";
    octx.fillRect(0, 0, out.width, out.height);
    octx.drawImage(c, 0, 0);
    const blob: Blob | null = await new Promise((r) => out.toBlob((b) => r(b), "image/png"));
    if (!blob) { setBusy(false); return; }
    try {
      await api.uploadMask(name, blob);
      setMsg(`Saved ${name}`);
      qc.invalidateQueries({ queryKey: ["masks"] });
    } catch (e) {
      setMsg(`Failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-wrap gap-3 items-center">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-ink-muted">Brush</span>
          <input
            type="range" min={4} max={200} value={brush}
            onChange={(e) => setBrush(parseInt(e.target.value, 10))}
          />
          <span className="font-mono w-8 text-right">{brush}</span>
        </div>
        <div className="flex gap-1">
          <button
            className={`nav-link ${mode === "draw" ? "active" : ""}`}
            onClick={() => setMode("draw")}
          >Draw</button>
          <button
            className={`nav-link ${mode === "erase" ? "active" : ""}`}
            onClick={() => setMode("erase")}
          >Erase</button>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-ink-muted">Name</span>
          <input
            className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm font-mono"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <button
          disabled={busy || !dims}
          onClick={save}
          className="ml-auto px-3 py-1.5 rounded-lg bg-accent text-bg-base font-medium disabled:opacity-50"
        >
          {busy ? "Saving…" : "Save mask"}
        </button>
        {msg && <div className="text-xs text-ink-dim">{msg}</div>}
      </div>

      <div className="card relative">
        {dims ? (
          <div className="relative w-full" style={{ aspectRatio: `${dims.width}/${dims.height}` }}>
            <img
              ref={baseRef}
              src={fileUrl.liveLatest()}
              alt="Latest frame"
              className="absolute inset-0 w-full h-full object-contain pointer-events-none"
            />
            <canvas
              ref={canvasRef}
              className="absolute inset-0 w-full h-full opacity-50 mix-blend-screen cursor-crosshair touch-none"
              onPointerDown={(e) => {
                dragging.current = true;
                const [x, y] = pointerToCanvas(e);
                paintAt(x, y);
                lastPt.current = [x, y];
                (e.target as Element).setPointerCapture(e.pointerId);
              }}
              onPointerMove={(e) => {
                if (!dragging.current) return;
                const [x, y] = pointerToCanvas(e);
                // Interpolate between points so fast strokes don't gap.
                if (lastPt.current) {
                  const [lx, ly] = lastPt.current;
                  const dx = x - lx, dy = y - ly;
                  const steps = Math.max(1, Math.ceil(Math.hypot(dx, dy) / (brush / 4)));
                  for (let i = 1; i <= steps; i++) {
                    paintAt(lx + (dx * i) / steps, ly + (dy * i) / steps);
                  }
                }
                lastPt.current = [x, y];
              }}
              onPointerUp={() => { dragging.current = false; lastPt.current = null; }}
              onPointerCancel={() => { dragging.current = false; lastPt.current = null; }}
            />
          </div>
        ) : (
          <div className="text-ink-dim text-sm">Waiting for a frame from the camera…</div>
        )}
      </div>

      <section className="card">
        <h3 className="text-sm uppercase tracking-wide text-ink-muted mb-2">Existing masks</h3>
        {data?.masks.length ? (
          <ul className="text-sm space-y-1 font-mono">
            {data.masks.map((m) => (
              <li key={m.name} className="flex justify-between">
                <span>{m.name}</span>
                <span className="text-ink-dim">{m.width}×{m.height}</span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-ink-dim text-sm">No masks yet.</div>
        )}
      </section>
    </div>
  );
}
