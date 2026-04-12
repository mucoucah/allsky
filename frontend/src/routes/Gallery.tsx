import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, fileUrl, ImageRow } from "../lib/api";

type Sort = "captured_at" | "filename" | "size_bytes" | "exposure_us" | "iso";

export default function Gallery() {
  const { data: days } = useQuery({ queryKey: ["days"], queryFn: api.days });
  const [date, setDate] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("captured_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");

  const activeDate = date ?? days?.dates[0] ?? null;

  const { data, isFetching } = useQuery({
    queryKey: ["images", activeDate, sort, order],
    queryFn: () => api.images({ date: activeDate!, sort, order, limit: 500 }),
    enabled: !!activeDate,
  });

  const grouped = useMemo(() => data?.items ?? [], [data]);

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-ink-muted text-sm">Date</span>
          <select
            className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm"
            value={activeDate ?? ""}
            onChange={(e) => setDate(e.target.value)}
          >
            {days?.dates.map((d) => (
              <option key={d} value={d}>{d}</option>
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
            <option value="captured_at">Captured time</option>
            <option value="filename">Filename</option>
            <option value="size_bytes">Size</option>
            <option value="exposure_us">Exposure</option>
            <option value="iso">ISO</option>
          </select>
          <button
            className="text-sm px-2 py-1 rounded-lg border border-bg-raised text-ink-muted"
            onClick={() => setOrder(order === "desc" ? "asc" : "desc")}
          >
            {order === "desc" ? "↓" : "↑"}
          </button>
        </div>
        <div className="text-ink-dim text-xs ml-auto">
          {isFetching ? "loading…" : data ? `${data.total} images` : ""}
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
        {grouped.map((row) => (
          <ImageCard key={row.path} row={row} />
        ))}
      </div>
    </div>
  );
}

function ImageCard({ row }: { row: ImageRow }) {
  return (
    <a
      href={fileUrl.imageFull(row.path)}
      target="_blank"
      rel="noreferrer"
      className="group relative aspect-square overflow-hidden rounded-xl border border-bg-raised bg-bg-panel"
    >
      <img
        loading="lazy"
        src={fileUrl.imageThumb(row.path)}
        alt={row.filename}
        className="w-full h-full object-cover group-hover:scale-105 transition-transform"
      />
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-2 text-[10px] font-mono text-ink-muted opacity-0 group-hover:opacity-100">
        <div className="truncate">{row.filename}</div>
        {row.exposure_us != null && (
          <div>{(row.exposure_us / 1000).toFixed(0)} ms</div>
        )}
      </div>
    </a>
  );
}
