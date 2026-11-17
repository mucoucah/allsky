import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Calendar, Film, Play, Trash2 } from "lucide-react";
import { api, type DailylapseFrame, type DailylapseOpts } from "../../lib/api";

const MODE_OPTIONS = [
  { value: "fixed", label: "Fixed clock time (UTC)" },
  { value: "sunrise", label: "Sunrise" },
  { value: "sunset", label: "Sunset" },
  { value: "solar_noon", label: "Solar noon" },
] as const;

export function DailyLapseSection() {
  const qc = useQueryClient();
  const [mode, setMode] = useState<string>("fixed");
  const [clockTime, setClockTime] = useState("12:00");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [maxOffset, setMaxOffset] = useState(30);
  const [fps, setFps] = useState(10);
  const [playUrl, setPlayUrl] = useState<string | null>(null);

  const buildOpts = (): DailylapseOpts => ({
    mode: mode as DailylapseOpts["mode"],
    clock_time: clockTime,
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    max_offset_min: maxOffset,
    fps,
    label: mode === "fixed" ? `fixed-${clockTime.replace(":", "")}` : mode,
  });

  const preview = useMutation({ mutationFn: () => api.dailylapsePreview(buildOpts()) });
  const generate = useMutation({
    mutationFn: () => api.dailylapseGenerate(buildOpts()),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["dailylapseList"] });
      setPlayUrl(data.video_url);
    },
  });
  const { data: videoList } = useQuery({
    queryKey: ["dailylapseList"],
    queryFn: api.dailylapseList,
  });
  const del = useMutation({
    mutationFn: api.dailylapseDelete,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dailylapseList"] }),
  });

  const apiBase = import.meta.env.VITE_API_BASE ?? "/api";

  return (
    <section className="card">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
        <Film size={20} className="text-accent" />
        Daily-Lapse
      </h2>
      <p className="text-xs text-ink-dim mb-4">
        Create a timelapse from one image per day at the same moment — track how the sun, moon, and stars
        move across your sky over weeks and months. Pick a fixed time, or use sunrise/sunset/solar noon
        which adjusts automatically for each day.
      </p>

      <div className="flex flex-col gap-4">
        {/* Time mode */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-ink-muted mb-1 font-medium">Capture moment</label>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="w-full bg-bg-base border border-bg-raised rounded-lg px-3 py-2 text-sm"
            >
              {MODE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          {mode === "fixed" && (
            <div>
              <label className="block text-xs text-ink-muted mb-1 font-medium">Time (UTC, 24h)</label>
              <input
                type="time"
                value={clockTime}
                onChange={(e) => setClockTime(e.target.value)}
                className="w-full bg-bg-base border border-bg-raised rounded-lg px-3 py-2 text-sm font-mono"
              />
            </div>
          )}
        </div>

        {/* Date range */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div>
            <label className="block text-xs text-ink-muted mb-1 font-medium">Start date</label>
            <input
              type="date"
              value={startDate ? `${startDate.slice(0,4)}-${startDate.slice(4,6)}-${startDate.slice(6,8)}` : ""}
              onChange={(e) => setStartDate(e.target.value.replace(/-/g, ""))}
              className="w-full bg-bg-base border border-bg-raised rounded-lg px-3 py-2 text-sm font-mono"
            />
          </div>
          <div>
            <label className="block text-xs text-ink-muted mb-1 font-medium">End date</label>
            <input
              type="date"
              value={endDate ? `${endDate.slice(0,4)}-${endDate.slice(4,6)}-${endDate.slice(6,8)}` : ""}
              onChange={(e) => setEndDate(e.target.value.replace(/-/g, ""))}
              className="w-full bg-bg-base border border-bg-raised rounded-lg px-3 py-2 text-sm font-mono"
            />
          </div>
          <div>
            <label className="block text-xs text-ink-muted mb-1 font-medium">Max offset (min)</label>
            <input
              type="number"
              value={maxOffset}
              min={1} max={120}
              onChange={(e) => setMaxOffset(Number(e.target.value))}
              className="w-full bg-bg-base border border-bg-raised rounded-lg px-3 py-2 text-sm font-mono"
            />
          </div>
          <div>
            <label className="block text-xs text-ink-muted mb-1 font-medium">FPS</label>
            <input
              type="number"
              value={fps}
              min={1} max={60}
              onChange={(e) => setFps(Number(e.target.value))}
              className="w-full bg-bg-base border border-bg-raised rounded-lg px-3 py-2 text-sm font-mono"
            />
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => preview.mutate()}
            disabled={preview.isPending}
            className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm inline-flex items-center gap-1.5"
          >
            <Calendar size={14} />
            {preview.isPending ? "Finding frames..." : "Preview frames"}
          </button>
          <button
            onClick={() => generate.mutate()}
            disabled={generate.isPending}
            className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium inline-flex items-center gap-1.5"
          >
            <Film size={14} />
            {generate.isPending ? "Generating..." : "Generate video"}
          </button>
        </div>

        {/* Preview results */}
        {preview.isSuccess && preview.data && (
          <div className="bg-bg-base rounded-lg border border-bg-raised p-3">
            <div className="text-sm font-medium mb-2">
              {preview.data.frame_count} frames found
              {preview.data.frames.length > 0 && (
                <span className="text-ink-dim ml-2">
                  ({preview.data.frames[0].date} – {preview.data.frames[preview.data.frames.length - 1].date})
                </span>
              )}
            </div>
            {preview.data.frames.length > 0 && (
              <div className="max-h-48 overflow-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-ink-muted border-b border-bg-raised">
                      <th className="text-left py-1 pr-2">Date</th>
                      <th className="text-left py-1 pr-2">Target</th>
                      <th className="text-left py-1 pr-2">Actual</th>
                      <th className="text-right py-1">Offset</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.data.frames.map((f: DailylapseFrame) => (
                      <tr key={f.date} className="border-b border-bg-raised/50">
                        <td className="py-1 pr-2 font-mono">{f.date}</td>
                        <td className="py-1 pr-2 font-mono">{f.target_time.slice(11, 16)}</td>
                        <td className="py-1 pr-2 font-mono">{f.actual_time.slice(11, 16)}</td>
                        <td className="py-1 text-right font-mono text-ink-dim">
                          {f.offset_sec < 60 ? `${f.offset_sec}s` : `${Math.round(f.offset_sec / 60)}m`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Generate result — inline player */}
        {playUrl && (
          <div className="bg-bg-base rounded-lg border border-bg-raised p-3">
            <div className="text-sm font-medium text-accent mb-2 flex items-center gap-1.5">
              <Play size={14} /> Now playing
            </div>
            <video
              key={playUrl}
              src={`${apiBase}${playUrl}`}
              controls
              autoPlay
              loop
              className="w-full rounded-lg max-h-[60vh]"
            />
          </div>
        )}

        {/* Previously generated videos */}
        {videoList && videoList.videos.length > 0 && (
          <div className="border-t border-bg-raised pt-3 mt-1">
            <div className="text-sm font-medium mb-2">Saved videos</div>
            <div className="flex flex-col gap-2">
              {videoList.videos.map((v) => (
                <div key={v.name} className="flex items-center justify-between bg-bg-base rounded-lg border border-bg-raised p-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Film size={14} className="text-ink-dim shrink-0" />
                    <span className="font-mono text-sm truncate">{v.name}</span>
                    <span className="text-xs text-ink-dim">{v.size_mb} MB</span>
                  </div>
                  <div className="flex items-center gap-1 shrink-0 ml-2">
                    <button
                      onClick={() => setPlayUrl(v.url)}
                      className="p-1.5 rounded-lg text-ink-muted hover:text-accent hover:bg-bg-raised"
                      title="Play"
                    >
                      <Play size={14} />
                    </button>
                    <button
                      onClick={() => del.mutate(v.url.split("/").pop()!)}
                      className="p-1.5 rounded-lg text-ink-muted hover:text-err hover:bg-bg-raised"
                      title="Delete"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
