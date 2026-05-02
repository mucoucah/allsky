import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  Wifi, Power, RefreshCw,
  Activity, Server, Clock, AlertTriangle, Zap, Camera, FolderOpen,
  PowerOff, RotateCcw, ChevronDown, ChevronUp,
} from "lucide-react";
import { api, AllskyDiskUsage } from "../lib/api";
import { StatusPill } from "../components/StatusPill";
import { UpdateSection, DarksSection, GenerateForDateSection, UploadSection } from "./Maintenance";

export default function System() {
  const { data: sys, refetch: refetchSys } = useQuery({
    queryKey: ["system"],
    queryFn: api.system,
    refetchInterval: 3_000,
  });

  const { data: allskyDisk } = useQuery({
    queryKey: ["allsky-disk"],
    queryFn: api.allskyDisk,
    staleTime: 30_000,
  });

  const control = useMutation({ mutationFn: api.serviceControl });
  const rebootMut = useMutation({ mutationFn: api.rebootPi });
  const shutdownMut = useMutation({ mutationFn: api.shutdownPi });

  const [confirmReboot, setConfirmReboot] = useState(false);
  const [confirmShutdown, setConfirmShutdown] = useState(false);
  const [showNetwork, setShowNetwork] = useState(false);

  const [logLines, setLogLines] = useState(200);
  const [logTab, setLogTab] = useState<"allsky" | "webui">("webui");
  const { data: logText, refetch: refetchLog, isFetching: logLoading } = useQuery({
    queryKey: ["log", logTab, logLines],
    queryFn: () => (logTab === "allsky" ? api.logTail(logLines) : api.logTailWebui(logLines)),
  });

  const h = sys?.host;
  const a = sys?.allsky;

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap">
        <Server size={22} className="text-accent" />
        <h1 className="text-xl font-semibold">System</h1>
        <button
          onClick={() => refetchSys()}
          className="ml-auto p-2 rounded-lg hover:bg-bg-raised text-ink-muted"
          title="Refresh"
        >
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Pi info + Allsky status */}
      {sys && (
        <div className="card flex flex-wrap gap-x-6 gap-y-2 items-center">
          {h?.pi_model && (
            <span className="text-sm font-medium">{h.pi_model}</span>
          )}
          <span className="text-sm text-ink-muted">{h?.hostname}</span>
          <span className="text-sm text-ink-muted">{h?.os}</span>
          <StatusPill status={a?.status ?? "Unknown"} />
          <span className="text-sm text-ink-muted">
            Allsky {a?.version}
          </span>
          <span className="text-sm text-ink-muted">
            <Camera size={14} className="inline mr-1" />
            {a?.camera.active_model || a?.camera.active || "No camera"}
          </span>
        </div>
      )}

      {/* Allsky service control */}
      <div className="card">
        <div className="flex flex-wrap gap-2 items-center">
          <h2 className="text-lg font-semibold mr-auto">Allsky Service</h2>
          {(["start", "stop", "restart", "status"] as const).map((v) => (
            <button
              key={v}
              disabled={control.isPending}
              onClick={() => control.mutate(v)}
              className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm hover:bg-bg-raised disabled:opacity-50 capitalize"
            >
              {v}
            </button>
          ))}
        </div>
        {control.data && (
          <div className={`mt-3 text-sm ${control.data.exit_code === 0 ? "text-ok" : "text-warn"}`}>
            {control.data.exit_code === 0
              ? `${control.data.verb} completed successfully.`
              : `${control.data.verb} returned code ${control.data.exit_code}.`}
            {control.data.stdout && (
              <pre className="text-xs font-mono text-ink-muted mt-2 whitespace-pre-wrap overflow-auto max-h-40">
                {control.data.stdout.trim()}
              </pre>
            )}
          </div>
        )}
      </div>

      {/* System monitors — horizontal bar charts */}
      {h && (
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">System Monitor</h2>
          <div className="flex flex-col gap-4">
            {/* CPU Temperature */}
            <BarMeter
              label="CPU Temperature"
              value={h.cpu_temp_c ?? 0}
              max={100}
              unit="°C"
              detail={`${h.cpu_info.cores_logical ?? "?"} cores \u00b7 ${h.cpu_info.architecture}`}
              thresholds={[65, 80]}
            />

            {/* CPU Usage */}
            <BarMeter
              label="CPU Usage"
              value={h.cpu_percent}
              max={100}
              unit="%"
              detail={`Load: ${h.load_avg["1m"].toFixed(2)} / ${h.load_avg["5m"].toFixed(2)} / ${h.load_avg["15m"].toFixed(2)}`}
              thresholds={[70, 90]}
            />

            {/* RAM */}
            <BarMeter
              label="Memory (RAM)"
              value={h.memory.percent}
              max={100}
              unit="%"
              detail={`${fmtBytes(h.memory.used)} used of ${fmtBytes(h.memory.total)} \u00b7 ${fmtBytes(h.memory.available)} free`}
              thresholds={[75, 90]}
            />

            {/* Swap */}
            {h.swap.total > 0 && (
              <BarMeter
                label="Swap"
                value={h.swap.percent}
                max={100}
                unit="%"
                detail={`${fmtBytes(h.swap.used)} used of ${fmtBytes(h.swap.total)}`}
                thresholds={[50, 80]}
              />
            )}

            {/* Disk root */}
            <BarMeter
              label="Disk (/)"
              value={h.disk_root.percent}
              max={100}
              unit="%"
              detail={`${fmtBytes(h.disk_root.used)} used of ${fmtBytes(h.disk_root.total)} \u00b7 ${fmtBytes(h.disk_root.free)} free`}
              thresholds={[75, 90]}
            />

            {/* Disk data (if different mount) */}
            {h.disk.path !== "/" && (
              <BarMeter
                label={`Disk (${h.disk.path})`}
                value={h.disk.percent}
                max={100}
                unit="%"
                detail={`${fmtBytes(h.disk.used)} used of ${fmtBytes(h.disk.total)} \u00b7 ${fmtBytes(h.disk.free)} free`}
                thresholds={[75, 90]}
              />
            )}

            {/* Uptime */}
            <div className="flex items-center justify-between text-sm">
              <span className="text-ink-muted flex items-center gap-2">
                <Clock size={14} /> Uptime
              </span>
              <span className="font-mono">
                {fmtUptime(h.uptime_seconds)}
                <span className="text-ink-dim text-xs ml-2">
                  (boot: {new Date(h.boot_time * 1000).toLocaleString()})
                </span>
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Throttle warnings */}
      {h?.throttle && <ThrottleWarnings throttle={h.throttle} />}

      {/* Day/Night status — what Allsky uses to choose settings */}
      {h?.time && <DayNightSection time={h.time} />}

      {/* Throttle event history */}
      <ThrottleHistorySection />

      {/* Allsky storage breakdown */}
      {allskyDisk && <AllskyStorageBreakdown usage={allskyDisk} />}

      {/* Network */}
      {h && h.network.length > 0 && (
        <>
          <button
            className="text-lg font-semibold flex items-center gap-2 hover:text-accent transition-colors"
            onClick={() => setShowNetwork(!showNetwork)}
          >
            <Wifi size={18} /> Network
            {showNetwork ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          {showNetwork && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {h.network.map((iface) => (
                <div key={iface.name} className="card">
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`w-2 h-2 rounded-full ${iface.is_up ? "bg-green-500" : "bg-red-500"}`} />
                    <span className="font-mono font-medium">{iface.name}</span>
                    {iface.speed_mbps ? (
                      <span className="text-xs text-ink-dim">{iface.speed_mbps} Mbps</span>
                    ) : null}
                  </div>
                  {iface.addresses.map((addr, i) => (
                    <div key={i} className="text-sm font-mono text-ink-muted ml-4">
                      {addr.address}
                      {addr.netmask && <span className="text-ink-dim"> / {addr.netmask}</span>}
                    </div>
                  ))}
                  {(iface.bytes_sent != null || iface.bytes_recv != null) && (
                    <div className="text-xs text-ink-dim mt-1 ml-4">
                      TX: {fmtBytes(iface.bytes_sent ?? 0)} &nbsp; RX: {fmtBytes(iface.bytes_recv ?? 0)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Power controls */}
      <h2 className="text-lg font-semibold flex items-center gap-2">
        <Power size={18} /> Power Management
      </h2>
      <div className="card flex flex-wrap gap-3">
        {!confirmReboot ? (
          <button
            onClick={() => setConfirmReboot(true)}
            className="px-4 py-2 rounded-lg bg-amber-600/20 border border-amber-600/40 text-amber-400 hover:bg-amber-600/30 flex items-center gap-2 text-sm font-medium"
          >
            <RotateCcw size={16} /> Reboot Pi
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-sm text-warn">Are you sure?</span>
            <button
              onClick={() => { rebootMut.mutate(); setConfirmReboot(false); }}
              disabled={rebootMut.isPending}
              className="px-3 py-1.5 rounded-lg bg-amber-600 text-white text-sm font-medium hover:bg-amber-700 disabled:opacity-50"
            >
              Yes, reboot
            </button>
            <button
              onClick={() => setConfirmReboot(false)}
              className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm"
            >
              Cancel
            </button>
          </div>
        )}

        {!confirmShutdown ? (
          <button
            onClick={() => setConfirmShutdown(true)}
            className="px-4 py-2 rounded-lg bg-red-600/20 border border-red-600/40 text-red-400 hover:bg-red-600/30 flex items-center gap-2 text-sm font-medium"
          >
            <PowerOff size={16} /> Shutdown Pi
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-sm text-red-400">Are you sure? You will need physical access to turn it back on.</span>
            <button
              onClick={() => { shutdownMut.mutate(); setConfirmShutdown(false); }}
              disabled={shutdownMut.isPending}
              className="px-3 py-1.5 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-50"
            >
              Yes, shutdown
            </button>
            <button
              onClick={() => setConfirmShutdown(false)}
              className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm"
            >
              Cancel
            </button>
          </div>
        )}

        {(rebootMut.data || shutdownMut.data) && (
          <div className="w-full text-sm text-ok">
            {rebootMut.data?.message || shutdownMut.data?.message}
          </div>
        )}
        {(rebootMut.error || shutdownMut.error) && (
          <div className="w-full text-sm text-red-400">
            {String(rebootMut.error || shutdownMut.error)}
          </div>
        )}
      </div>

      {/* Log viewer */}
      <div className="card">
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <h2 className="text-lg font-semibold">Logs</h2>
          {/* Tab buttons */}
          <div className="flex gap-1">
            {(["webui", "allsky"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setLogTab(tab)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                  logTab === tab
                    ? "bg-accent/20 text-accent border border-accent/40"
                    : "bg-bg-raised text-ink-muted hover:text-ink"
                }`}
              >
                {tab === "webui" ? "Web UI" : "Allsky Camera"}
              </button>
            ))}
          </div>
          <select
            className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm"
            value={logLines}
            onChange={(e) => setLogLines(parseInt(e.target.value, 10))}
          >
            <option value="100">100 lines</option>
            <option value="200">200 lines</option>
            <option value="500">500 lines</option>
            <option value="1000">1000 lines</option>
          </select>
          <button
            onClick={() => refetchLog()}
            disabled={logLoading}
            className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm disabled:opacity-50"
          >
            {logLoading ? "Refreshing\u2026" : "Refresh"}
          </button>
        </div>
        <pre className="text-xs font-mono whitespace-pre-wrap text-ink-muted overflow-auto max-h-96 bg-bg-base rounded-xl p-3 border border-bg-raised">
          {logLoading ? "Loading..." : logText || "(no log output)"}
        </pre>
      </div>

      {/* ── Maintenance ──────────────────────────────────────────── */}
      <div className="border-t border-bg-raised pt-4 mt-2">
        <h2 className="text-lg font-semibold mb-4">Maintenance</h2>
        <div className="flex flex-col gap-6 max-w-4xl">
          <UpdateSection />
          <DarksSection />
          <GenerateForDateSection />
          <UploadSection />
        </div>
      </div>

      {/* System info footer */}
      {h && (
        <div className="text-xs text-ink-dim flex flex-wrap gap-4 mt-4">
          <span>Python {h.python_version}</span>
          <span>Hostname: {h.hostname}</span>
          <span>OS: {h.os}</span>
        </div>
      )}
    </div>
  );
}

/* ── Sub-components ────────────────────────────────────────────── */

function ThrottleWarnings({ throttle }: { throttle: NonNullable<import("../lib/api").SystemSnapshot["host"]["throttle"]> }) {
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
          {anyActive ? "Active throttling detected" : "Throttling occurred since boot"}
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

function AllskyStorageBreakdown({ usage }: { usage: AllskyDiskUsage }) {
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
        <span className="font-medium text-sm">Allsky Storage Breakdown</span>
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

function BarMeter({ label, value, max, unit, detail, thresholds }: {
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

function DayNightSection({ time }: { time: NonNullable<import("../lib/api").SystemSnapshot["host"]["time"]> }) {
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

function ThrottleHistorySection() {
  const qc = useQuery({
    queryKey: ["throttle-history"],
    queryFn: api.throttleHistory,
    refetchInterval: 10_000,
  });
  const clearMut = useMutation({
    mutationFn: api.clearThrottleHistory,
  });

  if (!qc.data) return null;
  const events = qc.data.events;
  if (events.length === 0) {
    return (
      <div className="card text-xs text-ink-dim">
        <span className="font-medium text-ink">Throttle event log:</span>
        {" "}No throttle events recorded since the web service started.
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Zap size={14} className="text-amber-400" />
          Throttle event log ({events.length})
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

/* ── Helpers ────────────────────────────────────────────────────── */

function fmtBytes(n: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}

function fmtUptime(s: number): string {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}
