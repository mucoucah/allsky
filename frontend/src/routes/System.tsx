import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Tile } from "../components/Tile";
import { StatusPill } from "../components/StatusPill";

export default function System() {
  const { data: sys } = useQuery({
    queryKey: ["system"],
    queryFn: api.system,
    refetchInterval: 5_000,
  });

  const control = useMutation({ mutationFn: api.serviceControl });

  const [logLines, setLogLines] = useState(200);
  const { data: logText, refetch: refetchLog, isFetching: logLoading } = useQuery({
    queryKey: ["log", logLines],
    queryFn: () => api.logTail(logLines),
    enabled: false,
  });

  return (
    <div className="flex flex-col gap-4">
      {/* Status overview */}
      {sys && (
        <div className="card flex items-center gap-4 flex-wrap">
          <StatusPill status={sys.allsky.status} />
          <span className="text-sm text-ink-muted">
            Allsky {sys.allsky.version}
          </span>
          <span className="text-sm text-ink-muted">
            Camera: {sys.allsky.camera.active_model || sys.allsky.camera.active || "—"}
          </span>
        </div>
      )}

      {/* Service control */}
      <div className="card flex flex-wrap gap-2 items-center">
        <h2 className="text-lg font-semibold mr-auto">Service control</h2>
        {(["start", "stop", "restart", "status"] as const).map((v) => (
          <button
            key={v}
            disabled={control.isPending}
            onClick={() => control.mutate(v)}
            className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm hover:bg-bg-raised disabled:opacity-50"
          >
            {v}
          </button>
        ))}
      </div>

      {control.data && (
        <div className={`card text-sm ${control.data.exit_code === 0 ? "text-ok" : "text-warn"}`}>
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

      {/* System tiles */}
      {sys && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Tile
            label="CPU temp"
            value={sys.host.cpu_temp_c?.toFixed(1) ?? "—"}
            hint="°C"
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
          <Tile label="CPU usage" value={`${sys.host.cpu_percent.toFixed(0)} %`} />
          <Tile
            label="Memory"
            value={`${sys.host.memory.percent.toFixed(0)} %`}
            hint={fmtBytes(sys.host.memory.available) + " free"}
            status={sys.host.memory.percent < 85 ? "ok" : sys.host.memory.percent < 95 ? "warn" : "err"}
          />
          <Tile
            label="Disk"
            value={`${sys.host.disk.percent.toFixed(0)} %`}
            hint={fmtBytes(sys.host.disk.free) + " free"}
            status={sys.host.disk.percent < 80 ? "ok" : sys.host.disk.percent < 92 ? "warn" : "err"}
          />
          <Tile label="Load 1m" value={sys.host.load_avg["1m"].toFixed(2)} />
          <Tile label="Load 5m" value={sys.host.load_avg["5m"].toFixed(2)} />
          <Tile label="Load 15m" value={sys.host.load_avg["15m"].toFixed(2)} />
          <Tile
            label="Uptime"
            value={fmtUptime(sys.host.uptime_seconds)}
          />
        </div>
      )}

      {/* Log viewer */}
      <div className="card">
        <div className="flex items-center gap-3 mb-2">
          <h2 className="text-lg font-semibold">Allsky log</h2>
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
            {logLoading ? "Loading…" : logText ? "Refresh" : "Load log"}
          </button>
        </div>
        {logText && (
          <pre className="text-xs font-mono whitespace-pre-wrap text-ink-muted overflow-auto max-h-96 bg-bg-base rounded-xl p-3 border border-bg-raised">
            {logText}
          </pre>
        )}
      </div>
    </div>
  );
}

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
