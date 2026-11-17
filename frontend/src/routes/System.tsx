import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Camera, ChevronDown, ChevronUp, Power, PowerOff, RotateCcw, Server, Wifi } from "lucide-react";
import { api } from "../lib/api";
import { usePollInterval } from "../hooks/usePollInterval";
import { useCaptureOnly } from "../hooks/useCaptureOnly";
import { fmtBytes, fmtUptime } from "../lib/format";
import { StatusPill } from "../components/StatusPill";
import { PiHeartbeat, ProcessorSettings } from "../components/OffloadPanel";
import { UpdateSection } from "../sections/system/UpdateSection";
import {
  AllskyStorageBreakdown,
  BarMeter,
  DayNightSection,
  ThermalCard,
  ThrottleHistorySection,
  ThrottleWarnings,
} from "../sections/system/PcPanels";

export default function System() {
  const captureOnly = useCaptureOnly();
  const systemPoll = usePollInterval(15_000);
  const { data: sys, refetch: refetchSys } = useQuery({
    queryKey: ["system"],
    queryFn: api.system,
    refetchInterval: systemPoll,
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
  const { data: logText, refetch: refetchLog, isFetching: logLoading } = useQuery({
    queryKey: ["log", "webui", logLines],
    queryFn: () => api.logTailWebui(logLines),
  });

  const h = sys?.host;
  const a = sys?.allsky;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Server size={22} className="text-accent" />
        <h1 className="text-xl font-semibold">System</h1>
        <button onClick={() => refetchSys()} className="ml-auto text-xs text-ink-muted">Refresh</button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PiHeartbeat />
        <div className="card flex flex-col gap-3">
          <h2 className="text-lg font-semibold">PC</h2>
          {sys && (
            <>
              <div className="text-sm text-ink-muted">{h?.hostname} · {h?.os}</div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-ink-muted">Web UI host</span>
                <span className="font-mono text-xs">{h?.python_version}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-ink-muted">PC uptime</span>
                <span className="font-mono">{h ? fmtUptime(h.uptime_seconds) : "—"}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-ink-muted">Allsky</span>
                <span className="flex items-center gap-2">
                  <StatusPill status={a?.status ?? "Unknown"} />
                  <span className="text-xs">{a?.version}</span>
                </span>
              </div>
              <div className="text-sm text-ink-muted">
                <Camera size={14} className="inline mr-1" />
                {a?.camera.active_model || a?.camera.active || "No camera reported on this PC"}
              </div>
            </>
          )}
          {!captureOnly && (
            <div className="flex flex-wrap gap-2 pt-2 border-t border-bg-raised">
              {(["start", "stop", "restart", "status"] as const).map((v) => (
                <button
                  key={v}
                  disabled={control.isPending}
                  onClick={() => control.mutate(v)}
                  className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm capitalize disabled:opacity-50"
                >
                  {v}
                </button>
              ))}
            </div>
          )}
          {captureOnly && (
            <p className="text-xs text-ink-dim">
              Capture-only: this PC does not start or stop the Pi camera service.
            </p>
          )}
          {control.data && (
            <div className={`text-sm ${control.data.exit_code === 0 ? "text-ok" : "text-warn"}`}>
              {control.data.verb} returned {control.data.exit_code}.
            </div>
          )}
        </div>
      </div>

      <ThermalCard />
      <ProcessorSettings />

      {h && (
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">PC meters</h2>
          <div className="flex flex-col gap-4">
            <BarMeter label="PC CPU temperature" value={h.cpu_temp_c ?? 0} max={100} unit="°C" detail={`${h.cpu_info.cores_logical ?? "?"} cores · ${h.cpu_info.architecture}`} thresholds={[65, 80]} />
            <BarMeter label="PC CPU usage" value={h.cpu_percent} max={100} unit="%" detail={`Load ${h.load_avg["1m"].toFixed(2)} / ${h.load_avg["5m"].toFixed(2)} / ${h.load_avg["15m"].toFixed(2)}`} thresholds={[70, 90]} />
            <BarMeter label="PC memory" value={h.memory.percent} max={100} unit="%" detail={`${fmtBytes(h.memory.used)} used of ${fmtBytes(h.memory.total)}`} thresholds={[75, 90]} />
            {h.swap.total > 0 && (
              <BarMeter label="PC swap" value={h.swap.percent} max={100} unit="%" detail={`${fmtBytes(h.swap.used)} used of ${fmtBytes(h.swap.total)}`} thresholds={[50, 80]} />
            )}
            <BarMeter label="PC disk (/)" value={h.disk_root.percent} max={100} unit="%" detail={`${fmtBytes(h.disk_root.free)} free of ${fmtBytes(h.disk_root.total)}`} thresholds={[75, 90]} />
            {h.disk.path !== "/" && (
              <BarMeter label={`PC disk (${h.disk.path})`} value={h.disk.percent} max={100} unit="%" detail={`${fmtBytes(h.disk.free)} free of ${fmtBytes(h.disk.total)}`} thresholds={[75, 90]} />
            )}
          </div>
        </div>
      )}

      {h?.time && <DayNightSection time={h.time} />}
      {h?.throttle && <ThrottleWarnings throttle={h.throttle} />}
      <ThrottleHistorySection />
      {allskyDisk && <AllskyStorageBreakdown usage={allskyDisk} />}

      {h && h.network.length > 0 && (
        <>
          <button className="text-lg font-semibold flex items-center gap-2" onClick={() => setShowNetwork(!showNetwork)}>
            <Wifi size={18} /> PC network
            {showNetwork ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          {showNetwork && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {h.network.map((iface) => (
                <div key={iface.name} className="card">
                  <div className="font-mono font-medium">{iface.name}</div>
                  {iface.addresses.map((addr, i) => (
                    <div key={i} className="text-sm font-mono text-ink-muted">{addr.address}</div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {!captureOnly && (
        <div className="card flex flex-wrap gap-3">
          <h2 className="w-full text-lg font-semibold flex items-center gap-2">
            <Power size={18} /> This PC
          </h2>
          <p className="w-full text-xs text-ink-dim">
            These buttons reboot or shut down the machine running the web UI.
          </p>
          {!confirmReboot ? (
            <button onClick={() => setConfirmReboot(true)} className="px-4 py-2 rounded-lg bg-amber-600/20 border border-amber-600/40 text-amber-400 text-sm inline-flex items-center gap-2">
              <RotateCcw size={16} /> Reboot this PC
            </button>
          ) : (
            <button onClick={() => { rebootMut.mutate(); setConfirmReboot(false); }} className="px-3 py-1.5 rounded-lg bg-amber-600 text-white text-sm">
              Yes, reboot this PC
            </button>
          )}
          {!confirmShutdown ? (
            <button onClick={() => setConfirmShutdown(true)} className="px-4 py-2 rounded-lg bg-red-600/20 border border-red-600/40 text-red-400 text-sm inline-flex items-center gap-2">
              <PowerOff size={16} /> Shut down this PC
            </button>
          ) : (
            <button onClick={() => { shutdownMut.mutate(); setConfirmShutdown(false); }} className="px-3 py-1.5 rounded-lg bg-red-600 text-white text-sm">
              Yes, shut down this PC
            </button>
          )}
          {(rebootMut.data || shutdownMut.data) && (
            <div className="w-full text-sm text-ok">{rebootMut.data?.message || shutdownMut.data?.message}</div>
          )}
        </div>
      )}

      <div className="card">
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <h2 className="text-lg font-semibold">PC web UI log</h2>
          <select
            className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm"
            value={logLines}
            onChange={(e) => setLogLines(parseInt(e.target.value, 10))}
          >
            <option value="100">100 lines</option>
            <option value="200">200 lines</option>
            <option value="500">500 lines</option>
          </select>
          <button onClick={() => refetchLog()} disabled={logLoading} className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm">
            {logLoading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        <pre className="text-xs font-mono whitespace-pre-wrap text-ink-muted overflow-auto max-h-96 bg-bg-base rounded-xl p-3 border border-bg-raised">
          {logLoading ? "Loading..." : logText || "(no log output)"}
        </pre>
      </div>

      <UpdateSection />
    </div>
  );
}
