import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Wrench, Play, Square, Zap, AlertTriangle, CloudRain, X } from "lucide-react";
import { api, fileUrl } from "../lib/api";
import { useLiveSocket } from "../hooks/useLiveSocket";
import { Tile } from "../components/Tile";
import { StatusPill } from "../components/StatusPill";
import { SkyCard } from "../components/SkyCard";

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

export default function Dashboard() {
  const qc = useQueryClient();
  const { frameUrl, meta, connected } = useLiveSocket();
  const [fullscreen, setFullscreen] = useState(false);

  // Close fullscreen on Escape.
  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setFullscreen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullscreen]);

  // Cache-bust the HTTP fallback image every 5 seconds (when WS not connected).
  const [bust, setBust] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setBust(Date.now()), 5_000);
    return () => clearInterval(id);
  }, []);

  // Throttle banner dismissal state (stored in sessionStorage).
  const [throttleDismissed, setThrottleDismissed] = useState<string>(
    () => sessionStorage.getItem("throttleDismissedTs") || ""
  );
  function dismissThrottle(key: string) {
    sessionStorage.setItem("throttleDismissedTs", key);
    setThrottleDismissed(key);
  }

  const serviceAction = useMutation({
    mutationFn: api.serviceControl,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["system"] });
      qc.invalidateQueries({ queryKey: ["setupStatus"] });
    },
  });

  const { data: sys } = useQuery({
    queryKey: ["system"],
    queryFn: api.system,
    refetchInterval: 5_000,
  });

  const { data: msgs } = useQuery({
    queryKey: ["messages"],
    queryFn: api.messages,
    refetchInterval: 15_000,
  });

  const { data: focus } = useQuery({
    queryKey: ["focusCurrent"],
    queryFn: api.currentFocus,
    refetchInterval: 10_000,
  });

  const { data: setupStatus } = useQuery({
    queryKey: ["setupStatus"],
    queryFn: api.setupStatus,
    staleTime: 60_000,
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* Setup banner for fresh installs */}
      {setupStatus && !setupStatus.has_camera && (
        <Link
          to="/setup"
          className="lg:col-span-3 card border-accent/40 bg-accent/5 flex items-center gap-4 hover:bg-accent/10 transition-colors"
        >
          <Wrench size={32} className="text-accent shrink-0" />
          <div>
            <div className="font-semibold text-accent">Camera not configured</div>
            <div className="text-sm text-ink-muted">
              Click here to run the setup wizard — detect your camera and configure initial settings.
            </div>
          </div>
        </Link>
      )}
      {/* Live view — spans 2 cols on desktop. */}
      <section className="card lg:col-span-2 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold">Live view</h2>
            <span className={`pill ${connected ? "pill-ok" : "pill-err"}`}>
              {connected ? "WS connected" : "disconnected"}
            </span>
          </div>
          <div className="text-xs text-ink-dim font-mono">
            {meta?.mtime ?? "—"}
          </div>
        </div>
        <div
          className="aspect-video w-full bg-bg-base rounded-xl overflow-hidden border border-bg-raised flex items-center justify-center cursor-pointer"
          onClick={() => setFullscreen(true)}
          title="Click for fullscreen"
        >
          {frameUrl ? (
            <img
              src={frameUrl}
              alt="Latest sky frame"
              className="w-full h-full object-contain"
            />
          ) : (
            <img
              src={fileUrl.liveLatest(bust)}
              alt="Latest sky frame (HTTP fallback)"
              className="w-full h-full object-contain opacity-70"
              onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
            />
          )}
        </div>
      </section>

      {/* Right column: Allsky status + SkyCard stacked */}
      <div className="flex flex-col gap-4">
        {/* Allsky status card */}
        <section className="card flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Allsky</h2>
        {sys ? (
          <>
            <div className="flex items-center justify-between">
              <span className="text-ink-muted text-sm">Status</span>
              <StatusPill status={sys.allsky.status} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-ink-muted text-sm">Version</span>
              <span className="font-mono text-sm">{sys.allsky.version}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-ink-muted text-sm">Camera</span>
              <span className="font-mono text-sm text-right">
                {sys.allsky.camera.active_model || sys.allsky.camera.active || "—"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-ink-muted text-sm">Uptime</span>
              <span className="font-mono text-sm">{fmtUptime(sys.host.uptime_seconds)}</span>
            </div>
            {/* Camera controls */}
            <div className="flex gap-2 mt-1 pt-2 border-t border-bg-raised">
              {sys.allsky.service_active ? (
                <>
                  <button
                    onClick={() => serviceAction.mutate("restart")}
                    disabled={serviceAction.isPending}
                    className="flex-1 px-3 py-1.5 rounded-lg border border-bg-raised text-sm hover:bg-bg-raised disabled:opacity-50"
                  >
                    Restart
                  </button>
                  <button
                    onClick={() => serviceAction.mutate("stop")}
                    disabled={serviceAction.isPending}
                    className="flex-1 px-3 py-1.5 rounded-lg border border-err/30 text-err text-sm hover:bg-err/10 disabled:opacity-50 inline-flex items-center justify-center gap-1"
                  >
                    <Square size={12} /> Stop
                  </button>
                </>
              ) : (
                <button
                  onClick={() => serviceAction.mutate("start")}
                  disabled={serviceAction.isPending}
                  className="flex-1 px-3 py-1.5 rounded-lg bg-ok text-bg-base text-sm font-medium disabled:opacity-50 inline-flex items-center justify-center gap-1"
                >
                  <Play size={14} /> Start camera
                </button>
              )}
            </div>
          </>
        ) : (
          <div className="text-ink-dim text-sm">loading…</div>
        )}
      </section>

      {/* Sun/Moon card — compact, below Allsky status */}
      {sys?.host.time && <SkyCard time={sys.host.time} />}
      </div>

      {/* Throttle alert banner — ACTIVE */}
      {sys?.host.throttle && (
        sys.host.throttle.under_voltage_now || sys.host.throttle.throttled_now ||
        sys.host.throttle.freq_capped_now || sys.host.throttle.soft_temp_limit_now
      ) && throttleDismissed !== "active-" + (sys.host as any)?.uptime_seconds && (
        <div className="lg:col-span-3 card border-red-500/50 bg-red-500/10 animate-pulse">
          <div className="flex items-start gap-3">
            <Zap size={24} className="text-red-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <div className="font-semibold text-red-400">Throttling Active</div>
              <div className="text-sm text-ink-muted flex flex-wrap gap-3 mt-1">
                {sys.host.throttle.under_voltage_now && <span>&#9889; Under-voltage &mdash; check power supply</span>}
                {sys.host.throttle.throttled_now && <span>&#9889; CPU throttled</span>}
                {sys.host.throttle.freq_capped_now && <span>&#9889; Frequency capped</span>}
                {sys.host.throttle.soft_temp_limit_now && <span>&#127777; Temperature limit</span>}
              </div>
              <div className="text-xs text-ink-dim mt-2 flex flex-wrap gap-3">
                <span>CPU: {sys.host.cpu_temp_c?.toFixed(1) ?? "?"}&deg;C</span>
                <span>Usage: {sys.host.cpu_percent?.toFixed(0) ?? "?"}%</span>
                <span>Doing: {(sys.host as any).current_activity ?? "unknown"}</span>
                <Link to="/system" className="text-accent hover:underline">View history &rarr;</Link>
              </div>
            </div>
            <button
              onClick={() => dismissThrottle("active-" + (sys.host as any)?.uptime_seconds)}
              className="p-1 text-ink-muted hover:text-ink rounded"
              title="Dismiss (will reappear if throttling continues)"
            >
              <X size={18} />
            </button>
          </div>
        </div>
      )}

      {/* Past throttle warning (not active now but occurred since boot) */}
      {sys?.host.throttle && !(
        sys.host.throttle.under_voltage_now || sys.host.throttle.throttled_now ||
        sys.host.throttle.freq_capped_now || sys.host.throttle.soft_temp_limit_now
      ) && (
        sys.host.throttle.under_voltage_occurred || sys.host.throttle.throttled_occurred ||
        sys.host.throttle.freq_capped_occurred || sys.host.throttle.soft_temp_limit_occurred
      ) && throttleDismissed !== "past-" + (sys.host as any)?.uptime_seconds && (
        <div className="lg:col-span-3 card border-amber-500/30 bg-amber-500/5 flex items-center gap-3">
          <AlertTriangle size={20} className="text-amber-400 shrink-0" />
          <div className="text-sm text-amber-400 flex-1">
            Throttling occurred since last boot &mdash;
            {sys.host.throttle.under_voltage_occurred && " under-voltage"}
            {sys.host.throttle.throttled_occurred && " throttled"}
            {sys.host.throttle.freq_capped_occurred && " freq-capped"}
            {sys.host.throttle.soft_temp_limit_occurred && " temp-limit"}
            .
            <Link to="/system" className="text-accent hover:underline ml-1">
              View history &rarr;
            </Link>
          </div>
          <button
            onClick={() => dismissThrottle("past-" + (sys.host as any)?.uptime_seconds)}
            className="p-1 text-ink-muted hover:text-ink rounded"
            title="Dismiss"
          >
            <X size={18} />
          </button>
        </div>
      )}

      {/* System tiles */}
      {sys && (
        <>
          <Tile
            label="CPU temperature"
            value={sys.host.cpu_temp_c != null ? `${sys.host.cpu_temp_c.toFixed(1)} °C` : "—"}
            hint={`load ${sys.host.load_avg["1m"].toFixed(2)}`}
            status={
              sys.host.cpu_temp_c == null
                ? undefined
                : sys.host.cpu_temp_c < 65
                ? "ok"
                : sys.host.cpu_temp_c < 80
                ? "warn"
                : "err"
            }
          />
          <Tile
            label="CPU usage"
            value={`${sys.host.cpu_percent.toFixed(0)} %`}
            hint={`mem ${sys.host.memory.percent.toFixed(0)} %`}
          />
          <Tile
            label="Disk free"
            value={fmtBytes(sys.host.disk.free)}
            hint={`${sys.host.disk.percent.toFixed(0)} % used · ${sys.host.disk.path}`}
            status={
              sys.host.disk.percent < 80 ? "ok" : sys.host.disk.percent < 92 ? "warn" : "err"
            }
          />
        </>
      )}

      {/* Focus quality tile */}
      {focus && focus.score != null && (
        <Tile
          label="Focus quality"
          value={focus.score.toFixed(0)}
          hint={focus.baseline != null ? `baseline ${focus.baseline.toFixed(0)}` : "uncalibrated"}
          status={focus.status === "ok" ? "ok" : focus.status === "soft" ? "err" : undefined}
        />
      )}

      {/* Messages */}
      <section className="card lg:col-span-3">
        <h2 className="text-lg font-semibold mb-2">Recent messages</h2>
        {msgs && msgs.length > 0 ? (
          <ul className="divide-y divide-bg-raised text-sm">
            {msgs.slice().reverse().map((m, i) => (
              <li key={i} className="py-2 flex items-start gap-3">
                <span
                  className={`pill mt-0.5 ${
                    m.type === "error" ? "pill-err" : m.type === "warning" ? "pill-warn" : "pill-ok"
                  }`}
                >
                  {m.type}
                </span>
                <div className="flex-1">
                  <div className="text-xs text-ink-dim font-mono">{m.timestamp}</div>
                  <div
                    className="text-ink"
                    // upstream messages are HTML; the file is owned by allsky itself
                    dangerouslySetInnerHTML={{ __html: m.message }}
                  />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-ink-dim text-sm">No messages from Allsky.</div>
        )}
      </section>

      {/* Fullscreen image overlay */}
      {fullscreen && (
        <div
          className="fixed inset-0 z-50 bg-black flex items-center justify-center cursor-pointer"
          onClick={() => setFullscreen(false)}
        >
          <button
            onClick={() => setFullscreen(false)}
            className="absolute top-4 right-4 p-2 rounded-full bg-white/10 text-white z-10 hover:bg-white/20"
          >
            <X size={24} />
          </button>
          <img
            src={frameUrl || fileUrl.liveLatest(bust)}
            alt="Fullscreen sky view"
            className="max-h-screen max-w-screen object-contain"
          />
          <div className="absolute bottom-4 text-center text-sm text-white/50 font-mono">
            {meta?.mtime ?? ""} &mdash; Press Escape to close
          </div>
        </div>
      )}
    </div>
  );
}
