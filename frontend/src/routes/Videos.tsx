import { useState, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  X, ChevronLeft, ChevronRight, Search, ArrowUpDown,
  Calendar, Film, Download, Clock, HardDrive,
} from "lucide-react";
import { api, fileUrl } from "../lib/api";

type SortField = "date" | "name" | "size";
type SortOrder = "asc" | "desc";

interface VideoItem {
  name: string;
  size_bytes: number;
  mtime: number;
  date: string | null;
}

export default function Videos() {
  const [dateFilter, setDateFilter] = useState<string>("");
  const [sortBy, setSortBy] = useState<SortField>("date");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [search, setSearch] = useState("");
  const [playerVideo, setPlayerVideo] = useState<VideoItem | null>(null);
  const [playerIndex, setPlayerIndex] = useState(0);

  const { data, isLoading } = useQuery({
    queryKey: ["videos", dateFilter, sortBy, sortOrder],
    queryFn: () =>
      api.videos({
        date: dateFilter || undefined,
        sort: sortBy,
        order: sortOrder,
      }),
  });

  const items = (data?.items ?? []).filter(
    (v) => !search || v.name.toLowerCase().includes(search.toLowerCase()),
  );
  const dates = data?.dates ?? [];

  const openPlayer = useCallback(
    (idx: number) => {
      setPlayerVideo(items[idx]);
      setPlayerIndex(idx);
    },
    [items],
  );

  const closePlayer = useCallback(() => setPlayerVideo(null), []);

  const goPrev = useCallback(() => {
    if (playerIndex > 0) {
      setPlayerIndex(playerIndex - 1);
      setPlayerVideo(items[playerIndex - 1]);
    }
  }, [playerIndex, items]);

  const goNext = useCallback(() => {
    if (playerIndex < items.length - 1) {
      setPlayerIndex(playerIndex + 1);
      setPlayerVideo(items[playerIndex + 1]);
    }
  }, [playerIndex, items]);

  useEffect(() => {
    if (!playerVideo) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") closePlayer();
      else if (e.key === "ArrowLeft") goPrev();
      else if (e.key === "ArrowRight") goNext();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [playerVideo, closePlayer, goPrev, goNext]);

  function toggleSort(field: SortField) {
    if (sortBy === field) {
      setSortOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(field);
      setSortOrder("desc");
    }
  }

  function formatSize(bytes: number) {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatDate(ts: number) {
    return new Date(ts * 1000).toLocaleString();
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <Film size={22} className="text-accent" />
        <h1 className="text-xl font-semibold">Timelapse Videos</h1>
        {data && (
          <span className="text-xs text-ink-dim ml-auto">
            {data.total} video{data.total !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Filters bar */}
      <div className="card flex flex-wrap gap-3 items-center">
        {/* Search */}
        <div className="relative flex-1 min-w-[180px]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
          <input
            type="text"
            placeholder="Search filenames..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input pl-9 w-full"
          />
        </div>

        {/* Date picker */}
        <div className="relative min-w-[160px]">
          <Calendar size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
          <select
            value={dateFilter}
            onChange={(e) => setDateFilter(e.target.value)}
            className="input pl-9 w-full appearance-none"
          >
            <option value="">All dates</option>
            {dates.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>

        {/* Sort buttons */}
        <div className="flex gap-1">
          {(["date", "name", "size"] as SortField[]).map((field) => (
            <button
              key={field}
              onClick={() => toggleSort(field)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1 transition-colors ${
                sortBy === field
                  ? "bg-accent/20 text-accent border border-accent/40"
                  : "bg-bg-raised text-ink-muted hover:text-ink"
              }`}
            >
              {field === "date" && <Clock size={12} />}
              {field === "name" && <ArrowUpDown size={12} />}
              {field === "size" && <HardDrive size={12} />}
              {field.charAt(0).toUpperCase() + field.slice(1)}
              {sortBy === field && (
                <span className="text-[10px]">{sortOrder === "asc" ? "\u2191" : "\u2193"}</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Video grid */}
      {isLoading ? (
        <div className="card text-ink-dim text-sm">Loading videos...</div>
      ) : items.length === 0 ? (
        <div className="card text-ink-dim text-sm">
          {search || dateFilter
            ? "No videos match your filters."
            : "No timelapse videos yet. Videos will appear here after nightly generation runs."}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((video, idx) => (
            <div
              key={video.name}
              className="card p-0 overflow-hidden group cursor-pointer hover:ring-2 hover:ring-accent/50 transition-all"
              onClick={() => openPlayer(idx)}
            >
              {/* Video preview — shows first frame */}
              <div className="relative bg-black aspect-video flex items-center justify-center">
                <video
                  src={fileUrl.video(video.name)}
                  preload="metadata"
                  className="w-full h-full object-contain"
                />
                <div className="absolute inset-0 flex items-center justify-center bg-black/30 group-hover:bg-black/10 transition-colors">
                  <div className="w-12 h-12 rounded-full bg-accent/80 flex items-center justify-center">
                    <svg viewBox="0 0 24 24" className="w-6 h-6 text-white fill-current ml-0.5">
                      <polygon points="5,3 19,12 5,21" />
                    </svg>
                  </div>
                </div>
              </div>

              {/* Info */}
              <div className="p-3 flex flex-col gap-1">
                <div className="text-sm font-mono truncate" title={video.name}>
                  {video.name}
                </div>
                <div className="flex items-center justify-between text-xs text-ink-muted">
                  <span>{video.date ?? "Unknown date"}</span>
                  <span>{formatSize(video.size_bytes)}</span>
                </div>
                <div className="text-[10px] text-ink-dim">
                  {formatDate(video.mtime)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Fullscreen video player */}
      {playerVideo && (
        <div
          className="fixed inset-0 z-50 bg-black/95 flex flex-col items-center justify-center"
          onClick={closePlayer}
        >
          {/* Close */}
          <button
            onClick={closePlayer}
            className="absolute top-4 right-4 p-2 rounded-full bg-bg-panel/60 text-ink z-10 hover:bg-bg-panel"
          >
            <X size={24} />
          </button>

          {/* Prev */}
          {playerIndex > 0 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                goPrev();
              }}
              className="absolute left-4 top-1/2 -translate-y-1/2 p-2 rounded-full bg-bg-panel/60 text-ink z-10 hover:bg-bg-panel"
            >
              <ChevronLeft size={28} />
            </button>
          )}

          {/* Next */}
          {playerIndex < items.length - 1 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                goNext();
              }}
              className="absolute right-4 top-1/2 -translate-y-1/2 p-2 rounded-full bg-bg-panel/60 text-ink z-10 hover:bg-bg-panel"
            >
              <ChevronRight size={28} />
            </button>
          )}

          {/* Player */}
          <video
            key={playerVideo.name}
            src={fileUrl.video(playerVideo.name)}
            controls
            autoPlay
            className="max-h-[85vh] max-w-[95vw] rounded-lg"
            onClick={(e) => e.stopPropagation()}
          />

          {/* Info bar */}
          <div
            className="mt-3 flex items-center gap-4 text-sm text-ink-muted"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="font-mono">{playerVideo.name}</span>
            <span>{playerVideo.date ?? ""}</span>
            <span>{formatSize(playerVideo.size_bytes)}</span>
            <span>
              {playerIndex + 1} / {items.length}
            </span>
            <a
              href={fileUrl.video(playerVideo.name)}
              download
              className="flex items-center gap-1 text-accent hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              <Download size={14} />
              Download
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
