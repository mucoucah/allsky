import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, Plus, Trash2, MousePointer, Layers } from "lucide-react";
import { api, fileUrl } from "../lib/api";

interface OverlayField {
  id: string;
  label: string;
  tlx: number;
  tly: number;
  x?: number;
  y?: number;
  fontsize?: number;
  fill?: string;
  format?: string;
  strokewidth?: number;
  sample?: string;
  [key: string]: unknown;
}

interface OverlayLayout {
  fields: OverlayField[];
  images?: any[];
  settings?: Record<string, unknown>;
  fonts?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

interface AvailableField {
  id: number;
  name: string; // e.g. "${DATE}"
  description: string;
  format: string;
  sample: string;
  type: string;
  source: string;
}

export default function OverlayEditor() {
  const qc = useQueryClient();
  const { data: cfg, isLoading } = useQuery({
    queryKey: ["overlay-config"],
    queryFn: api.overlayConfig,
  });

  const [selectedLayout, setSelectedLayout] = useState<string>("overlay-RPi.json");
  const { data: layout } = useQuery({
    queryKey: ["overlay-layout", selectedLayout],
    queryFn: () => api.overlayLayout(selectedLayout),
    enabled: !!selectedLayout,
  });

  const [localLayout, setLocalLayout] = useState<OverlayLayout | null>(null);
  useEffect(() => {
    if (layout) setLocalLayout(JSON.parse(JSON.stringify(layout)));
  }, [layout]);

  const [selectedFieldId, setSelectedFieldId] = useState<string | null>(null);
  const [imageNaturalSize, setImageNaturalSize] = useState<{ w: number; h: number }>({ w: 1920, h: 1080 });
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [dragging, setDragging] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () => api.saveOverlayLayout(selectedLayout, localLayout),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["overlay-layout", selectedLayout] }),
  });

  // Available fields from fields.json
  const availableFields: AvailableField[] = useMemo(() => {
    // fields.json has { data: [...] } structure
    const fields = cfg?.fields as any;
    if (fields?.data && Array.isArray(fields.data)) return fields.data;
    if (Array.isArray(fields)) return fields;
    return [];
  }, [cfg]);

  function displayRatio() {
    if (!imgRef.current) return 1;
    return imgRef.current.clientWidth / imageNaturalSize.w;
  }

  function onMouseMove(e: React.MouseEvent) {
    if (!dragging || !localLayout || !containerRef.current || !imgRef.current) return;
    const rect = imgRef.current.getBoundingClientRect();
    const ratio = displayRatio();
    const nativeX = (e.clientX - rect.left) / ratio;
    const nativeY = (e.clientY - rect.top) / ratio;
    setLocalLayout({
      ...localLayout,
      fields: localLayout.fields.map((f) =>
        f.id === dragging
          ? { ...f, tlx: Math.round(Math.max(0, Math.min(imageNaturalSize.w, nativeX))),
                    tly: Math.round(Math.max(0, Math.min(imageNaturalSize.h, nativeY))) }
          : f,
      ),
    });
  }

  function updateField(id: string, updates: Partial<OverlayField>) {
    if (!localLayout) return;
    setLocalLayout({
      ...localLayout,
      fields: localLayout.fields.map((f) => (f.id === id ? { ...f, ...updates } : f)),
    });
  }

  function deleteField(id: string) {
    if (!localLayout) return;
    setLocalLayout({
      ...localLayout,
      fields: localLayout.fields.filter((f) => f.id !== id),
    });
    setSelectedFieldId(null);
  }

  function addField(fieldName: string) {
    if (!localLayout) return;
    const nextId = `oe-field-${Date.now()}`;
    const newField: OverlayField = {
      id: nextId,
      label: fieldName,
      tlx: 100,
      tly: 100,
      fontsize: 40,
      fill: "#ffffff",
      strokewidth: 0,
    };
    setLocalLayout({ ...localLayout, fields: [...localLayout.fields, newField] });
    setSelectedFieldId(nextId);
  }

  if (isLoading) return <div className="text-ink-dim">Loading overlay editor...</div>;

  if (!cfg?.exists) {
    return (
      <div className="card text-warn">
        <h2 className="text-lg font-semibold mb-2">Overlay config not found</h2>
        <p className="text-sm">
          Overlay templates are not installed. Run <code>sudo ./install.sh</code> to install them.
        </p>
      </div>
    );
  }

  const selected = localLayout?.fields.find((f) => f.id === selectedFieldId);

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex items-center gap-3 flex-wrap">
        <h1 className="text-lg font-semibold flex items-center gap-2">
          <Layers size={20} /> Overlay Editor
        </h1>
        <select
          value={selectedLayout}
          onChange={(e) => setSelectedLayout(e.target.value)}
          className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm"
        >
          {cfg.configs.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <span className="text-xs text-ink-dim">
          Drag fields to reposition. Click to edit. Overlays only apply when Overlay Method = module (in Settings).
        </span>
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending || !localLayout}
          className="ml-auto px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium inline-flex items-center gap-1.5"
        >
          <Save size={14} />
          {save.isPending ? "Saving..." : "Save"}
        </button>
        {save.isSuccess && <span className="text-xs text-ok">Saved</span>}
      </div>

      <div className="flex gap-4">
        {/* Canvas: image with draggable fields */}
        <div className="flex-1 card p-0 overflow-hidden" ref={containerRef}>
          <div
            className="relative bg-black"
            onMouseMove={onMouseMove}
            onMouseUp={() => setDragging(null)}
            onMouseLeave={() => setDragging(null)}
          >
            <img
              ref={imgRef}
              src={fileUrl.liveLatest()}
              alt="overlay preview"
              className="w-full block select-none"
              draggable={false}
              onLoad={(e) => {
                const img = e.currentTarget;
                setImageNaturalSize({ w: img.naturalWidth || 1920, h: img.naturalHeight || 1080 });
              }}
            />
            {localLayout?.fields.map((f) => {
              const ratio = displayRatio();
              const isSelected = f.id === selectedFieldId;
              const fontSize = (f.fontsize ?? 40) * ratio;
              return (
                <div
                  key={f.id}
                  className={`absolute cursor-move select-none ${
                    isSelected ? "ring-2 ring-accent" : "hover:ring-2 hover:ring-accent/50"
                  }`}
                  style={{
                    left: `${f.tlx * ratio}px`,
                    top: `${f.tly * ratio}px`,
                    color: f.fill || "#ffffff",
                    fontSize: `${Math.max(8, fontSize)}px`,
                    textShadow: "2px 2px 4px rgba(0,0,0,0.9)",
                    fontFamily: "monospace",
                    lineHeight: 1,
                    padding: "2px 4px",
                  }}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    setSelectedFieldId(f.id);
                    setDragging(f.id);
                  }}
                  onClick={() => setSelectedFieldId(f.id)}
                >
                  {renderFieldLabel(f)}
                </div>
              );
            })}
          </div>
        </div>

        {/* Sidebar */}
        <div className="w-80 flex flex-col gap-3">
          <div className="card">
            <h3 className="text-sm font-semibold mb-2 flex items-center gap-1">
              <Plus size={14} /> Add field
            </h3>
            <select
              className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-xs w-full"
              onChange={(e) => {
                if (e.target.value) {
                  addField(e.target.value);
                  e.target.value = "";
                }
              }}
              value=""
            >
              <option value="">Select a data field...</option>
              {availableFields.map((af) => (
                <option key={af.id} value={af.name}>
                  {af.name} — {af.description}
                </option>
              ))}
            </select>
            <p className="text-[10px] text-ink-dim mt-1">
              Or type custom label (e.g. "${"${DATE}"}  ${"${TIME}"}") in the field below after adding.
            </p>
          </div>

          {selected ? (
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold flex items-center gap-1">
                  <MousePointer size={14} /> Field: {selected.id}
                </h3>
                <button
                  onClick={() => deleteField(selected.id)}
                  className="p-1 text-err hover:bg-err/10 rounded"
                  title="Delete field"
                >
                  <Trash2 size={14} />
                </button>
              </div>
              <div className="flex flex-col gap-2 text-xs">
                <label className="flex flex-col gap-0.5">
                  <span className="text-ink-muted">Label (supports ${"${VAR}"})</span>
                  <input
                    type="text"
                    value={selected.label}
                    onChange={(e) => updateField(selected.id, { label: e.target.value })}
                    className="bg-bg-base border border-bg-raised rounded px-2 py-1 font-mono"
                  />
                </label>
                <label className="flex flex-col gap-0.5">
                  <span className="text-ink-muted">Format string</span>
                  <input
                    type="text"
                    value={selected.format ?? ""}
                    onChange={(e) => updateField(selected.id, { format: e.target.value })}
                    placeholder="e.g. {:.2f} or %H:%M:%S"
                    className="bg-bg-base border border-bg-raised rounded px-2 py-1 font-mono"
                  />
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <label className="flex flex-col gap-0.5">
                    <span className="text-ink-muted">X</span>
                    <input
                      type="number"
                      value={selected.tlx}
                      onChange={(e) => updateField(selected.id, { tlx: parseInt(e.target.value, 10) || 0 })}
                      className="bg-bg-base border border-bg-raised rounded px-2 py-1 font-mono"
                    />
                  </label>
                  <label className="flex flex-col gap-0.5">
                    <span className="text-ink-muted">Y</span>
                    <input
                      type="number"
                      value={selected.tly}
                      onChange={(e) => updateField(selected.id, { tly: parseInt(e.target.value, 10) || 0 })}
                      className="bg-bg-base border border-bg-raised rounded px-2 py-1 font-mono"
                    />
                  </label>
                  <label className="flex flex-col gap-0.5">
                    <span className="text-ink-muted">Font size</span>
                    <input
                      type="number"
                      value={selected.fontsize ?? 40}
                      onChange={(e) => updateField(selected.id, { fontsize: parseInt(e.target.value, 10) || 40 })}
                      className="bg-bg-base border border-bg-raised rounded px-2 py-1 font-mono"
                    />
                  </label>
                  <label className="flex flex-col gap-0.5">
                    <span className="text-ink-muted">Color</span>
                    <input
                      type="color"
                      value={selected.fill ?? "#ffffff"}
                      onChange={(e) => updateField(selected.id, { fill: e.target.value })}
                      className="bg-bg-base border border-bg-raised rounded px-1 py-1 h-[26px]"
                    />
                  </label>
                </div>
                <label className="flex flex-col gap-0.5">
                  <span className="text-ink-muted">Stroke width (outline)</span>
                  <input
                    type="number"
                    value={selected.strokewidth ?? 0}
                    onChange={(e) => updateField(selected.id, { strokewidth: parseInt(e.target.value, 10) || 0 })}
                    className="bg-bg-base border border-bg-raised rounded px-2 py-1 font-mono"
                  />
                </label>
              </div>
            </div>
          ) : (
            <div className="card text-xs text-ink-dim">
              Click a field on the image to edit its properties, or add a new field above.
            </div>
          )}

          <div className="card">
            <h3 className="text-sm font-semibold mb-2">All fields ({localLayout?.fields.length ?? 0})</h3>
            <ul className="text-xs space-y-1 max-h-80 overflow-auto">
              {localLayout?.fields.map((f) => (
                <li
                  key={f.id}
                  onClick={() => setSelectedFieldId(f.id)}
                  className={`cursor-pointer px-2 py-1 rounded truncate ${
                    f.id === selectedFieldId ? "bg-accent/20 text-accent" : "hover:bg-bg-raised"
                  }`}
                >
                  <span className="font-mono">{f.label}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function renderFieldLabel(f: OverlayField): string {
  // Replace upstream placeholders with sample values for preview.
  let label = f.label;
  // Simple preview — replace known placeholders with sample values.
  const samples: Record<string, string> = {
    "${DATE}": new Date().toLocaleDateString(),
    "${TIME}": new Date().toLocaleTimeString(),
    "${TEMPERATURE_C}": "20.0",
    "${TEMPERATURE_F}": "68.0",
    "${EXPOSURE_US}": "10000",
    "${sEXPOSURE}": "10 ms",
    "${GAIN}": "1.0",
    "${sAUTOGAIN}": "(auto)",
    "${sAUTOEXPOSURE}": "(auto)",
    "${CAMERA_TYPE}": "RPi",
    "${CAMERA_MODEL}": "imx290",
    "${MEAN}": "0.5",
    "${DAY_OR_NIGHT}": "DAY",
    "${ALLSKY_VERSION}": "v2024.12.06",
    "${SUN_ELEVATION}": "-6.0",
    "${MOON_ILLUMINATION}": "50.0",
  };
  for (const [k, v] of Object.entries(samples)) {
    label = label.split(k).join(v);
  }
  // Strip any remaining ${...} placeholders
  label = label.replace(/\$\{[^}]*\}/g, "?");
  return label || f.id;
}
