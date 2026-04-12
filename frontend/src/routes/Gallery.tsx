import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, ChevronLeft, ChevronRight, Download } from "lucide-react";
import { api, fileUrl, ImageRow } from "../lib/api";

type Sort = "captured_at" | "filename" | "size_bytes" | "exposure_us" | "iso";

export default function Gallery() {
  const { data: days } = useQuery({ queryKey: ["days"], queryFn: api.days });
  const [date, setDate] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("captured_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(0);
  const [lightbox, setLightbox] = useState<number | null>(null);
  const perPage = 120;

  const activeDate = date ?? days?.dates[0] ?? null;

  // Reset page on date/sort change.
  useEffect(() => setPage(0), [activeDate, sort, order]);

  const { data, isFetching } = useQuery({
    queryKey: ["images", activeDate, sort, order, page],
    queryFn: () =>
      api.images({ date: activeDate!, sort, order, limit: perPage, offset: page * perPage }),
    enabled: !!activeDate,
    placeholderData: (prev) => prev,
  });

  const items = useMemo(() => data?.items ?? [], [data]);
  const totalPages = data ? Math.ceil(data.total / perPage) : 0;

  // Keyboard nav in lightbox.
  const openLightbox = useCallback((i: number) => setLightbox(i), []);
  const closeLightbox = useCallback(() => setLightbox(null), []);
  const prev = useCallback(
    () => setLightbox((i) => (i !== null && i > 0 ? i - 1 : i)),
    [],
  );
  const next = useCallback(
    () => setLightbox((i) => (i !== null && i < items.length - 1 ? i + 1 : i)),
    [items.length],
  );

  useEffect(() => {
    if (lightbox === null) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") closeLightbox();
      else if (e.key === "ArrowLeft") prev();
      else if (e.key === "ArrowRight") next();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox, closeLightbox, prev, next]);

  return (
    <div className="flex flex-col gap-4">
      {/* Toolbar */}
      <div className="card flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-ink-muted text-sm">Date</span>
          <select
            className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm"
            value={activeDate ?? ""}
            onChange={(e) => setDate(e.target.value)}
          >
            {days?.dates.map((d) => (
              <option key={d} value={d}>
                {formatDate(d)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-ink-muted text-sm">Sort</span>
          <select
            className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm"
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
          >
            <option value="captured_at">Time</option>
            <option value="filename">Filename</option>
            <option value="size_bytes">Size</option>
            <option value="exposure_us">Exposure</option>
            <option value="iso">ISO</option>
          </select>
          <button
            className="text-sm px-2 py-1 rounded-lg border border-bg-raised text-ink-muted"
            onClick={() => setOrder(order === "desc" ? "asc" : "desc")}
          >
            {order === "desc" ? "↓ newest" : "↑ oldest"}
          </button>
        </div>

        {/* Pagination */}
        <div className="flex items-center gap-1 ml-auto">
          <button
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
            className="px-2 py-1 rounded-lg border border-bg-raised text-ink-muted text-sm disabled:opacity-30"
          >
            ‹
          </button>
          <span className="text-xs text-ink-dim px-2">
            {page + 1} / {totalPages || 1}
          </span>
          <button
            disabled={page >= totalPages - 1}
            onClick={() => setPage((p) => p + 1)}
            className="px-2 py-1 rounded-lg border border-bg-raised text-ink-muted text-sm disabled:opacity-30"
          >
            ›
          </button>
        </div>
        <div className="text-ink-dim text-xs">
          {isFetching ? "loading…" : data ? `${data.total} images` : ""}
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-8 gap-2">
        {items.map((row, i) => (
          <button
            key={row.path}
            onClick={() => openLightbox(i)}
            className="group relative aspect-square overflow-hidden rounded-xl border border-bg-raised bg-bg-panel focus:ring-2 focus:ring-accent"
          >
            <img
              loading="lazy"
              src={fileUrl.imageThumb(row.path)}
              alt={row.filename}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform"
            />
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-1.5 text-[9px] font-mono text-ink-muted opacity-0 group-hover:opacity-100 transition-opacity">
              <div className="truncate">{fmtTime(row.captured_at)}</div>
            </div>
          </button>
        ))}
      </div>

      {/* Lightbox */}
      {lightbox !== null && items[lightbox] && (
        <Lightbox
          row={items[lightbox]}
          onClose={closeLightbox}
          onPrev={lightbox > 0 ? prev : undefined}
          onNext={lightbox < items.length - 1 ? next : undefined}
          index={lightbox}
          total={data?.total ?? items.length}
        />
      )}
    </div>
  );
}

function Lightbox({
  row,
  onClose,
  onPrev,
  onNext,
  index,
  total,
}: {
  row: ImageRow;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  index: number;
  total: number;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 backdrop-blur flex items-center justify-center"
      onClick={onClose}
    >
      {/* Controls */}
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2 rounded-full bg-bg-panel/60 text-ink z-10"
      >
        <X size={24} />
      </button>

      {onPrev && (
        <button
          onClick={(e) => { e.stopPropagation(); onPrev(); }}
          className="absolute left-4 top-1/2 -translate-y-1/2 p-2 rounded-full bg-bg-panel/60 text-ink z-10"
        >
          <ChevronLeft size={28} />
        </button>
      )}
      {onNext && (
        <button
          onClick={(e) => { e.stopPropagation(); onNext(); }}
          className="absolute right-4 top-1/2 -translate-y-1/2 p-2 rounded-full bg-bg-panel/60 text-ink z-10"
        >
          <ChevronRight size={28} />
        </button>
      )}

      {/* Image */}
      <img
        src={fileUrl.imageFull(row.path)}
        alt={row.filename}
        className="max-h-[85vh] max-w-[90vw] object-contain rounded-lg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />

      {/* Metadata drawer */}
      <div
        className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/95 to-transparent p-4 md:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="max-w-3xl mx-auto flex flex-wrap gap-x-6 gap-y-1 text-sm font-mono text-ink-muted">
          <span>{row.filename}</span>
          <span>{fmtTime(row.captured_at)}</span>
          {row.exposure_us != null && (
            <span>{fmtExposure(row.exposure_us)}</span>
          )}
          {row.iso != null && <span>ISO {row.iso}</span>}
          {row.width != null && row.height != null && (
            <span>
              {row.width}×{row.height}
            </span>
          )}
          <span>{fmtBytes(row.size_bytes)}</span>
          <span className="text-ink-dim">
            {index + 1} / {total}
          </span>
          <a
            href={fileUrl.imageFull(row.path)}
            download
            className="inline-flex items-center gap-1 text-accent hover:underline"
          >
            <Download size={14} /> download
          </a>
        </div>
      </div>
    </div>
  );
}

function formatDate(yyyymmdd: string): string {
  if (yyyymmdd.length !== 8) return yyyymmdd;
  return `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6)}`;
}

function fmtTime(epoch: number): string {
  return new Date(epoch * 1000).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function fmtExposure(us: number): string {
  if (us >= 1_000_000) return `${(us / 1_000_000).toFixed(1)} s`;
  if (us >= 1_000) return `${(us / 1_000).toFixed(0)} ms`;
  return `${us} µs`;
}

function fmtBytes(n: number): string {
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}
