import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, Camera, FolderOpen, Zap } from "lucide-react";
import { api, type AllskyDiskUsage, type ThermalConfig } from "../../lib/api";
import { usePollInterval } from "../../hooks/usePollInterval";
import { fmtBytes } from "../../lib/format";

/* ── Sub-components ────────────────────────────────────────────── */

export function ThrottleWarnings({ throttle }: { throttle: NonNullable<import("../../lib/api").SystemSnapshot["host"]["throttle"]> }) {
  const warnings: Array<{ label: string; active: boolean; occurred: boolean }> = [
    { label: "Under-voltage", active: throttle.under_voltage_now, occurred: throttle.under_voltage_occurred },
    { label: "Frequency capped", active: throttle.freq_capped_now, occurred: throttle.freq_capped_occurred },
    { label: "Throttled", active: throttle.throttled_now, occurred: throttle.throttled_occurred },
    { label: "Soft temp limit", active: throttle.soft_temp_limit_now, occurred: throttle.soft_temp_limit_occurred },
  ];

  const anyActive = warnings.some((w) => w.active);
  const anyOccurred = warnings.some((w) => w.occurred);

  if (!anyActive && !anyOccurred) return null;

  return (
    <div className={`card border ${anyActive ? "border-red-500/50 bg-red-500/5" : "border-amber-500/30 bg-amber-500/5"}`}>
      <div className="flex items-center gap-2 mb-2">
        {anyActive ? <Zap size={16} className="text-red-400" /> : <AlertTriangle size={16} className="text-amber-400" />}
        <span className="font-medium text-sm">
          {anyActive ? "PC throttling active" : "PC throttling occurred since boot"}
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {warnings.map((w) => (
          <div key={w.label} className="text-xs">
            <span className={w.active ? "text-red-400 font-medium" : w.occurred ? "text-amber-400" : "text-ink-dim"}>
              {w.active ? "\u26a0 " : w.occurred ? "\u25cb " : "\u2713 "}
              {w.label}
            </span>
            {w.active && <span className="text-red-400 text-[10px] ml-1">(NOW)</span>}
            {!w.active && w.occurred && <span className="text-amber-400 text-[10px] ml-1">(past)</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function AllskyStorageBreakdown({ usage }: { usage: AllskyDiskUsage }) {
  const items = [
    { label: "Images", value: usage.images, icon: Camera },
    { label: "Darks", value: usage.darks, icon: FolderOpen },
    { label: "Keograms", value: usage.keograms, icon: Activity },
    { label: "Startrails", value: usage.startrails, icon: Activity },
    { label: "Videos", value: usage.videos, icon: FolderOpen },
    { label: "Config", value: usage.config, icon: FolderOpen },
    { label: "Temp", value: usage.tmp, icon: FolderOpen },
  ];

  const total = items.reduce((s, i) => s + i.value, 0);

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-3">
        <FolderOpen size={16} className="text-accent" />
        <span className="font-medium text-sm">PC storage</span>
        <span className="text-xs text-ink-dim ml-auto">Total: {fmtBytes(total)}</span>
      </div>
      {/* Bar visualization */}
      {total > 0 && (
        <div className="h-4 rounded-full overflow-hidden flex mb-3 bg-bg-base border border-bg-raised">
          {items.filter((i) => i.value > 0).map((item, idx) => (
            <div
              key={item.label}
              className={`h-full ${STORAGE_COLORS[idx % STORAGE_COLORS.length]}`}
              style={{ width: `${(item.value / total) * 100}%` }}
              title={`${item.label}: ${fmtBytes(item.value)}`}
            />
          ))}
        </div>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {items.map((item, idx) => (
          <div key={item.label} className="flex items-center gap-2 text-sm">
            <div className={`w-3 h-3 rounded-sm ${STORAGE_COLORS[idx % STORAGE_COLORS.length]}`} />
            <span className="text-ink-muted">{item.label}</span>
            <span className="ml-auto font-mono text-xs">{fmtBytes(item.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const STORAGE_COLORS = [
  "bg-blue-500", "bg-purple-500", "bg-emerald-500", "bg-amber-500",
  "bg-rose-500", "bg-cyan-500", "bg-orange-500",
];

/* ── Bar meter (horizontal bar chart like original allsky) ────── */

export function BarMeter({ label, value, max, unit, detail, thresholds }: {
  label: string;
  value: number;
  max: number;
  unit: string;
  detail?: string;
  thresholds?: [number, number]; // [warn, err]
}) {
  const pct = Math.min((value / max) * 100, 100);
  const [warnAt, errAt] = thresholds ?? [70, 90];
  const color = value >= errAt ? "bg-red-500" : value >= warnAt ? "bg-amber-500" : "bg-emerald-500";
  const textColor = value >= errAt ? "text-red-400" : value >= warnAt ? "text-amber-400" : "text-emerald-400";

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm text-ink-muted">{label}</span>
        <span className={`text-sm font-mono font-medium ${textColor}`}>
          {value.toFixed(value < 10 ? 1 : 0)}{unit}
        </span>
      </div>
      <div className="h-5 rounded-full overflow-hidden bg-bg-base border border-bg-raised relative">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${color}`}
          style={{ width: `${pct}%` }}
        />
        {/* Threshold markers */}
        <div
          className="absolute top-0 bottom-0 w-px bg-amber-500/30"
          style={{ left: `${(warnAt / max) * 100}%` }}
        />
        <div
          className="absolute top-0 bottom-0 w-px bg-red-500/30"
          style={{ left: `${(errAt / max) * 100}%` }}
        />
      </div>
      {detail && (
        <div className="text-[11px] text-ink-dim mt-0.5">{detail}</div>
      )}
    </div>
  );
}

/* ── Day/Night status ───────────────────────────────────────────── */

export function DayNightSection({ time }: { time: NonNullable<import("../../lib/api").SystemSnapshot["host"]["time"]> }) {
  const isDay = time.is_day;
  return (
    <div className={`card ${isDay ? "border-amber-500/30" : "border-indigo-500/30"}`}>
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
        Day/Night Status &mdash;{" "}
        <span className={isDay ? "text-amber-400" : "text-indigo-300"}>
          {time.day_night_status || (isDay ? "DAY" : "NIGHT")}
        </span>
        <span className="text-xs text-ink-muted font-normal">
          (Allsky is using {isDay ? "daytime" : "nighttime"} settings)
        </span>
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1 text-xs">
        <div className="text-ink-muted">System time</div>
        <div className="font-mono md:col-span-2">
          {new Date(time.system_time).toLocaleString()}{" "}
          <span className="text-ink-dim">{time.timezone_name ?? time.timezone}</span>
        </div>
        <div className="text-ink-muted">UTC</div>
        <div className="font-mono md:col-span-2">
          {new Date(time.utc_time).toUTCString()}
        </div>
        {time.latitude !== null && time.longitude !== null && (
          <>
            <div className="text-ink-muted">Location</div>
            <div className="font-mono md:col-span-2">
              {time.latitude?.toFixed(4)}, {time.longitude?.toFixed(4)}
            </div>
          </>
        )}
        <div className="text-ink-muted">Sun elevation</div>
        <div className="font-mono md:col-span-2">
          {time.sun_elevation_deg?.toFixed(2) ?? "?"}&deg;
          {time.sun_azimuth_deg !== undefined && (
            <span className="text-ink-dim"> (az {time.sun_azimuth_deg.toFixed(0)}&deg;)</span>
          )}
        </div>
        <div className="text-ink-muted">Day/night threshold</div>
        <div className="font-mono md:col-span-2">
          {String(time.day_night_angle ?? -6)}&deg; sun elevation
        </div>
        {time.next_sunrise_local && (
          <>
            <div className="text-ink-muted">Next sunrise</div>
            <div className="font-mono md:col-span-2">
              {new Date(time.next_sunrise_local).toLocaleString()}
            </div>
          </>
        )}
        {time.next_sunset_local && (
          <>
            <div className="text-ink-muted">Next sunset</div>
            <div className="font-mono md:col-span-2">
              {new Date(time.next_sunset_local).toLocaleString()}
            </div>
          </>
        )}
        {time.moon && (
          <>
            <div className="text-ink-muted">Moon phase</div>
            <div className="font-mono md:col-span-2">
              {time.moon.phase_name} &mdash; {time.moon.illumination_pct.toFixed(0)}% illuminated
              {time.moon.is_visible && <span className="text-ink-dim"> (visible, elev {time.moon.elevation_deg.toFixed(0)}&deg;)</span>}
            </div>
          </>
        )}
      </div>
      {time.sun_calc_error && (
        <div className="text-xs text-err mt-2">Sun calc error: {time.sun_calc_error}</div>
      )}
      {time.sun_elevation_note && (
        <div className="text-xs text-warn mt-2">{time.sun_elevation_note}</div>
      )}
    </div>
  );
}

/* ── Throttle history ───────────────────────────────────────────── */

export function ThermalCard() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["thermal"],
    queryFn: api.thermal,
    refetchInterval: usePollInterval(15_000),
  });
  const [draft, setDraft] = useState<Partial<ThermalConfig> | null>(null);
  const save = useMutation({
    mutationFn: api.setThermal,
    onSuccess: () => {
      setDraft(null);
      qc.invalidateQueries({ queryKey: ["thermal"] });
      qc.invalidateQueries({ queryKey: ["system"] });
    },
  });
  if (!data) return null;
  const d = { ...data, ...(draft ?? {}) };
  const state = data.state ?? "ok";
  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-center gap-2 flex-wrap">
        <h2 className="text-lg font-semibold">PC thermal guard</h2>
        <span className={`text-xs font-medium ${
          state === "stopped" ? "text-err" : state === "warm" ? "text-warn" : "text-ok"
        }`}>
          {state}
          {data.temp_c != null ? ` · ${Number(data.temp_c).toFixed(1)} °C` : ""}
        </span>
      </div>
      <p className="text-xs text-ink-dim">{data.message}</p>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={Boolean(d.enabled)}
            onChange={(e) => setDraft({ ...d, enabled: e.target.checked })}
          />
          Enabled
        </label>
        {([
          ["warn_c", "Warm °C"],
          ["stop_c", "Stop °C"],
          ["resume_c", "Resume °C"],
          ["poll_seconds", "Poll seconds"],
          ["warm_extra_delay_ms", "Extra delay ms"],
        ] as const).map(([key, label]) => (
          <label key={key} className="text-xs text-ink-dim">
            {label}
            <input
              type="number"
              className="mt-1 w-full rounded-lg bg-bg-base border border-bg-raised px-2 py-1 text-sm text-ink"
              value={Number(d[key] ?? 0)}
              onChange={(e) => setDraft({ ...d, [key]: Number(e.target.value) })}
            />
          </label>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <button
          disabled={!draft || save.isPending}
          onClick={() => draft && save.mutate(draft)}
          className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save thresholds"}
        </button>
        {save.isError && <span className="text-xs text-err">Check the values (resume &lt; warm &lt; stop, poll 30–60 s).</span>}
        {save.isSuccess && <span className="text-xs text-ok">Saved</span>}
      </div>
    </div>
  );
}

export function ThrottleHistorySection() {
  const qc = useQuery({
    queryKey: ["throttle-history"],
    queryFn: api.throttleHistory,
    refetchInterval: usePollInterval(15_000),
  });
  const clearMut = useMutation({
    mutationFn: api.clearThrottleHistory,
  });

  if (!qc.data) return null;
  const events = qc.data.events;
  if (events.length === 0) {
    return (
      <div className="card text-xs text-ink-dim">
        <span className="font-medium text-ink">PC throttle event log:</span>
        {" "}No throttle events recorded since the web service started.
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Zap size={14} className="text-amber-400" />
          PC throttle event log ({events.length})
        </h3>
        <button
          onClick={async () => {
            await clearMut.mutateAsync();
            qc.refetch();
          }}
          className="text-[10px] text-accent hover:underline"
        >
          Clear history
        </button>
      </div>
      <div className="text-xs divide-y divide-bg-raised max-h-60 overflow-auto">
        {events.map((e, i) => (
          <div key={i} className="py-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-ink-muted font-mono">
              {new Date(e.ts * 1000).toLocaleString()}
            </span>
            <span className="text-red-400 font-medium">
              {e.types.map(t => t.replace(/_/g, " ")).join(", ")}
            </span>
            {e.cpu_temp_c != null && (
              <span className="text-ink-muted">{e.cpu_temp_c.toFixed(1)}&deg;C</span>
            )}
            {e.cpu_percent != null && (
              <span className="text-ink-muted">CPU {e.cpu_percent.toFixed(0)}%</span>
            )}
            <span className="text-ink-dim italic">while: {e.activity}</span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-ink-dim mt-2">
        History is kept in memory since the web service started. Restarting the service clears it.
      </p>
    </div>
  );
}

