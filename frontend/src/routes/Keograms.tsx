import { useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, ChevronLeft, ChevronRight } from "lucide-react";
import { api, fileUrl } from "../lib/api";

export default function Keograms() {
  const { data: keo } = useQuery({ queryKey: ["keograms"], queryFn: api.keograms });
  const { data: trails } = useQuery({ queryKey: ["startrails"], queryFn: api.startrails });
  const [viewer, setViewer] = useState<{ items: Item[]; index: number } | null>(null);

  const close = useCallback(() => setViewer(null), []);
  const prev = useCallback(
    () => setViewer((v) => v && v.index > 0 ? { ...v, index: v.index - 1 } : v),
    [],
  );
  const next = useCallback(
    () => setViewer((v) => v && v.index < v.items.length - 1 ? { ...v, index: v.index + 1 } : v),
    [],
  );

  useEffect(() => {
    if (!viewer) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
      else if (e.key === "ArrowLeft") prev();
      else if (e.key === "ArrowRight") next();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [viewer, close, prev, next]);

  type Item = { name: string; mtime: number; url: string };

  const keoItems: Item[] = (keo?.items ?? []).map((i) => ({
    ...i,
    url: fileUrl.keogram(i.name),
  }));
  const trailItems: Item[] = (trails?.items ?? []).map((i) => ({
    ...i,
    url: fileUrl.startrail(i.name),
  }));

  return (
    <div className="flex flex-col gap-6">
      <div className="card bg-accent/5 border-accent/20 text-sm">
        <p className="mb-1"><strong>Keograms</strong> take a vertical slice from the center of every image captured during the night and join them horizontally to show how the sky changed over time. The wider it is, the more images were captured. A narrow keogram means few images.</p>
        <p><strong>Startrails</strong> stack all night images, keeping the brightest pixel at each point — stars appear as arcs around the celestial pole. Airplane/satellite trails also show up as straight lines.</p>
        <p className="text-xs text-ink-dim mt-1">These are generated automatically at sunrise (<code>endOfNight.sh</code>). You can re-generate them for a past date from the <strong>Maintenance</strong> page.</p>
        <p className="text-xs text-ink-dim mt-1"><strong>Mask note:</strong> the upstream <code>keogram</code>/<code>startrails</code> binaries process the full image — they do not accept an external mask. Bright objects outside the area of interest (tree branches, eaves, streetlights) will still appear. The mask <em>is</em> used for meteor/focus/rain detection.</p>
      </div>
      <Section
        title="Keograms"
        items={keoItems}
        onOpen={(idx) => setViewer({ items: keoItems, index: idx })}
      />
      <Section
        title="Startrails"
        items={trailItems}
        onOpen={(idx) => setViewer({ items: trailItems, index: idx })}
      />

      {viewer && viewer.items[viewer.index] && (
        <FullscreenViewer
          item={viewer.items[viewer.index]}
          onClose={close}
          onPrev={viewer.index > 0 ? prev : undefined}
          onNext={viewer.index < viewer.items.length - 1 ? next : undefined}
          index={viewer.index}
          total={viewer.items.length}
        />
      )}
    </div>
  );
}

function Section(props: {
  title: string;
  items: Array<{ name: string; mtime: number; url: string }>;
  onOpen: (idx: number) => void;
}) {
  return (
    <section className="card">
      <h2 className="text-lg font-semibold mb-3">{props.title}</h2>
      {props.items.length ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {props.items.map((it, idx) => (
            <button
              key={it.name}
              onClick={() => props.onOpen(idx)}
              className="rounded-xl overflow-hidden border border-bg-raised bg-bg-base text-left group focus:ring-2 focus:ring-accent"
            >
              <img
                loading="lazy"
                src={it.url}
                alt={it.name}
                className="w-full h-36 object-cover group-hover:scale-105 transition-transform"
              />
              <div className="p-2 flex items-center justify-between">
                <span className="text-xs font-mono text-ink-muted truncate">
                  {it.name}
                </span>
                <span className="text-[10px] text-ink-dim">
                  {new Date(it.mtime * 1000).toLocaleDateString()}
                </span>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div className="text-ink-dim text-sm">none yet</div>
      )}
    </section>
  );
}

function FullscreenViewer(props: {
  item: { name: string; url: string };
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  index: number;
  total: number;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center"
      onClick={props.onClose}
    >
      <button
        onClick={props.onClose}
        className="absolute top-4 right-4 p-2 rounded-full bg-bg-panel/60 text-ink z-10"
      >
        <X size={24} />
      </button>
      {props.onPrev && (
        <button
          onClick={(e) => { e.stopPropagation(); props.onPrev!(); }}
          className="absolute left-4 top-1/2 -translate-y-1/2 p-2 rounded-full bg-bg-panel/60 text-ink z-10"
        >
          <ChevronLeft size={28} />
        </button>
      )}
      {props.onNext && (
        <button
          onClick={(e) => { e.stopPropagation(); props.onNext!(); }}
          className="absolute right-4 top-1/2 -translate-y-1/2 p-2 rounded-full bg-bg-panel/60 text-ink z-10"
        >
          <ChevronRight size={28} />
        </button>
      )}
      <img
        src={props.item.url}
        alt={props.item.name}
        className="max-h-[90vh] max-w-[95vw] object-contain"
        onClick={(e) => e.stopPropagation()}
      />
      <div
        className="absolute bottom-4 inset-x-0 text-center text-sm font-mono text-ink-muted"
        onClick={(e) => e.stopPropagation()}
      >
        {props.item.name} — {props.index + 1} / {props.total}
      </div>
    </div>
  );
}
