import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { CloudRain, Play, Square, Wrench, X, Zap } from "lucide-react";
import { api, fileUrl } from "../lib/api";
import { useLiveSocket } from "../hooks/useLiveSocket";
import { usePollInterval } from "../hooks/usePollInterval";
import { useCaptureOnly } from "../hooks/useCaptureOnly";
import { fmtBytes, fmtUptime } from "../lib/format";
import { Tile } from "../components/Tile";
import { StatusPill } from "../components/StatusPill";
import { SkyCard } from "../components/SkyCard";
import { PiHeartbeat } from "../components/OffloadPanel";

export default function Live() {
  const qc = useQueryClient();
  const captureOnly = useCaptureOnly();
  const { frameUrl, meta, connected } = useLiveSocket();
  const [fullscreen, setFullscreen] = useState(false);
  const poll = usePollInterval(30_000);
  const [bust, setBust] = useState(Date.now());
  const [throttleDismissed, setThrottleDismissed] = useState<string>(
    () => sessionStorage.getItem("throttleDismissedTs") || "",
  );

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setFullscreen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullscreen]);

  useEffect(() => {
    if (poll === false) return;
    const id = setInterval(() => setBust(Date.now()), poll);
    return () => clearInterval(id);
  }, [poll]);

  const serviceAction = useMutation({
    mutationFn: api.serviceControl,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["system"] });
      qc.invalidateQueries({ queryKey: ["setupStatus"] });
    },
  });

  const { data: sys } = useQuery({ queryKey: ["system"], queryFn: api.system, refetchInterval: poll });
  const { data: pi } = useQuery({ queryKey: ["offload-pi"], queryFn: api.offloadPi, refetchInterval: poll });
  const { data: msgs } = useQuery({ queryKey: ["messages"], queryFn: api.messages, refetchInterval: poll });
  const { data: setupStatus } = useQuery({ queryKey: ["setupStatus"], queryFn: api.setupStatus, staleTime: 60_000 });
  const { data: alerts } = useQuery({
    queryKey: ["alerts"],
    queryFn: api.alerts,
    refetchInterval: poll ? 60_000 : false,
  });
  const ackAlert = useMutation({
    mutationFn: api.ackAlert,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  const rainAlert = useMemo(() => {
    if (!alerts) return null;
    const cutoff = Date.now() / 1000 - 6 * 3600;
    return alerts.find((a) => a.source === "rain" && a.acknowledged_at == null && a.created_at >= cutoff) ?? null;
  }, [alerts]);

  const piStatus = pi?.status;
  const piHot = piStatus?.thermal_state === "stopped" || piStatus?.thermal_state === "warm"
    || piStatus?.throttled?.throttled_now || piStatus?.throttled?.soft_temp_limit_now;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {sys?.host.thermal && sys.host.thermal.state !== "ok" && (
        <div className={`lg:col-span-3 card flex items-start gap-3 ${
          sys.host.thermal.state === "stopped" ? "border-err/40 bg-err/10" : "border-warn/40 bg-warn/10"
        }`}>
          <Zap size={22} className={sys.host.thermal.state === "stopped" ? "text-err" : "text-warn"} />
          <div>
            <div className="font-semibold">
              PC thermal: {sys.host.thermal.state === "stopped" ? "processing paused — CPU too hot" : "CPU warm — processing slowed"}
            </div>
            <div className="text-sm text-ink-muted mt-0.5">
              {sys.host.thermal.message}
              {sys.host.thermal.temp_c != null && ` (${sys.host.thermal.temp_c.toFixed(1)} °C)`}
            </div>
          </div>
        </div>
      )}

      {piHot && piStatus && (
        <div className="lg:col-span-3 card border-warn/40 bg-warn/10 flex items-start gap-3">
          <Zap size={22} className="text-warn" />
          <div>
            <div className="font-semibold">Pi thermal: {piStatus.thermal_state ?? "check the heartbeat"}</div>
            <div className="text-sm text-ink-muted mt-0.5">
              {piStatus.temp_c != null ? `${piStatus.temp_c.toFixed(1)} °C` : "No temperature in the heartbeat."}
              {piStatus.throttled?.raw ? ` · throttle ${piStatus.throttled.raw}` : ""}
            </div>
          </div>
        </div>
      )}

      {setupStatus && !setupStatus.has_camera && !captureOnly && (
        <Link to="/setup" className="lg:col-span-3 card border-accent/40 bg-accent/5 flex items-center gap-4 hover:bg-accent/10">
          <Wrench size={32} className="text-accent shrink-0" />
          <div>
            <div className="font-semibold text-accent">Camera not configured</div>
            <div className="text-sm text-ink-muted">Open the setup wizard to detect the camera.</div>
          </div>
        </Link>
      )}

      {rainAlert && (
        <div className="lg:col-span-3 card border-sky-400/40 bg-sky-400/10 flex items-start gap-3">
          <CloudRain size={24} className="text-sky-300 shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="font-semibold text-sky-300">Rain / moisture detected on dome</div>
            <div className="text-sm text-ink-muted mt-0.5">{rainAlert.message}</div>
            <div className="text-xs text-ink-dim mt-1">
              {new Date(rainAlert.created_at * 1000).toLocaleString()}
              <Link to="/extras#rain" className="text-accent hover:underline ml-3">Adjust sensitivity</Link>
            </div>
          </div>
          <button onClick={() => ackAlert.mutate(rainAlert.id)} className="p-1 text-ink-muted hover:text-ink rounded" title="Dismiss">
            <X size={18} />
          </button>
        </div>
      )}

      <section className="card lg:col-span-2 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold">Live view</h2>
            <span className={`pill ${connected ? "pill-ok" : "pill-err"}`}>
              {connected ? "WS connected" : "disconnected"}
            </span>
          </div>
          <div className="text-xs text-ink-dim font-mono">{meta?.mtime ?? "—"}</div>
        </div>
        <div
          className="aspect-video w-full bg-bg-base rounded-xl overflow-hidden border border-bg-raised flex items-center justify-center cursor-pointer"
          onClick={() => setFullscreen(true)}
        >
          <img
            src={frameUrl || fileUrl.liveLatest(bust)}
            alt="Latest sky frame"
            className="w-full h-full object-contain"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        </div>
      </section>

      <div className="flex flex-col gap-4">
        <section className="card flex flex-col gap-3">
          <h2 className="text-lg font-semibold">Tonight</h2>
          {sys ? (
            <>
              <div className="flex items-center justify-between">
                <span className="text-ink-muted text-sm">Capture</span>
                <StatusPill status={sys.allsky.status} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-muted text-sm">Camera</span>
                <span className="font-mono text-sm text-right">
                  {sys.allsky.camera.active_model || sys.allsky.camera.active || "—"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-muted text-sm">PC uptime</span>
                <span className="font-mono text-sm">{fmtUptime(sys.host.uptime_seconds)}</span>
              </div>
              {!captureOnly && (
                <div className="flex gap-2 mt-1 pt-2 border-t border-bg-raised">
                  {sys.allsky.service_active ? (
                    <>
                      <button
                        onClick={() => serviceAction.mutate("restart")}
                        disabled={serviceAction.isPending}
                        className="flex-1 px-3 py-1.5 rounded-lg border border-bg-raised text-sm disabled:opacity-50"
                      >
                        Restart
                      </button>
                      <button
                        onClick={() => serviceAction.mutate("stop")}
                        disabled={serviceAction.isPending}
                        className="flex-1 px-3 py-1.5 rounded-lg border border-err/30 text-err text-sm disabled:opacity-50 inline-flex items-center justify-center gap-1"
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
              )}
              {captureOnly && (
                <p className="text-xs text-ink-dim">
                  Capture-only: the Pi runs the camera. Start and stop stay on the Pi.
                </p>
              )}
            </>
          ) : (
            <div className="text-ink-dim text-sm">loading…</div>
          )}
        </section>
        <PiHeartbeat />
        {sys?.host.time && <SkyCard time={sys.host.time} />}
      </div>

      {sys?.host.throttle && (
        sys.host.throttle.under_voltage_now || sys.host.throttle.throttled_now ||
        sys.host.throttle.freq_capped_now || sys.host.throttle.soft_temp_limit_now
      ) && (
        <div className="lg:col-span-3 card border-red-500/50 bg-red-500/10">
          <div className="font-semibold text-red-400">PC throttling active</div>
          <div className="text-sm text-ink-muted mt-1">
            This is the PC running the web UI, not the Pi.
            <Link to="/system" className="text-accent hover:underline ml-2">System</Link>
          </div>
        </div>
      )}

      {sys && (
        <>
          <Tile
            label="PC CPU temperature"
            value={sys.host.cpu_temp_c != null ? `${sys.host.cpu_temp_c.toFixed(1)} °C` : "—"}
            hint={`load ${sys.host.load_avg["1m"].toFixed(2)}`}
            status={
              sys.host.cpu_temp_c == null ? undefined
                : sys.host.cpu_temp_c < 65 ? "ok"
                : sys.host.cpu_temp_c < 80 ? "warn" : "err"
            }
          />
          <Tile label="PC CPU usage" value={`${sys.host.cpu_percent.toFixed(0)} %`} hint={`mem ${sys.host.memory.percent.toFixed(0)} %`} />
          <Tile
            label="PC disk free"
            value={fmtBytes(sys.host.disk.free)}
            hint={`${sys.host.disk.percent.toFixed(0)} % used · ${sys.host.disk.path}`}
            status={sys.host.disk.percent < 80 ? "ok" : sys.host.disk.percent < 92 ? "warn" : "err"}
          />
        </>
      )}

      <section className="card lg:col-span-3">
        <h2 className="text-lg font-semibold mb-2">Recent messages</h2>
        {msgs && msgs.length > 0 ? (
          <ul className="divide-y divide-bg-raised text-sm">
            {msgs.slice().reverse().map((m, i) => (
              <li key={i} className="py-2 flex items-start gap-3">
                <span className={`pill mt-0.5 ${m.type === "error" ? "pill-err" : m.type === "warning" ? "pill-warn" : "pill-ok"}`}>
                  {m.type}
                </span>
                <div className="flex-1">
                  <div className="text-xs text-ink-dim font-mono">{m.timestamp}</div>
                  <div dangerouslySetInnerHTML={{ __html: m.message }} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-ink-dim text-sm">No messages from Allsky.</div>
        )}
      </section>

      {fullscreen && (
        <div className="fixed inset-0 z-50 bg-black flex items-center justify-center" onClick={() => setFullscreen(false)}>
          <button className="absolute top-4 right-4 p-2 text-white" onClick={() => setFullscreen(false)}><X size={24} /></button>
          <img src={frameUrl || fileUrl.liveLatest(bust)} alt="Fullscreen sky view" className="max-h-screen max-w-screen object-contain" />
        </div>
      )}
    </div>
  );
}
