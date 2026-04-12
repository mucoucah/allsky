import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Tile } from "../components/Tile";

export default function System() {
  const { data: sys } = useQuery({
    queryKey: ["system"],
    queryFn: api.system,
    refetchInterval: 5_000,
  });

  const control = useMutation({ mutationFn: api.serviceControl });

  return (
    <div className="flex flex-col gap-4">
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
        <pre className="card text-xs font-mono whitespace-pre-wrap text-ink-muted overflow-auto max-h-60">
          {`$ systemctl ${control.data.verb} allsky.service\nexit ${control.data.exit_code}\n${control.data.stdout}${control.data.stderr}`}
        </pre>
      )}

      {sys && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Tile label="CPU temp" value={sys.host.cpu_temp_c?.toFixed(1) ?? "—"} hint="°C" />
          <Tile label="CPU usage" value={`${sys.host.cpu_percent.toFixed(0)} %`} />
          <Tile label="Memory" value={`${sys.host.memory.percent.toFixed(0)} %`} />
          <Tile label="Disk" value={`${sys.host.disk.percent.toFixed(0)} %`} hint={sys.host.disk.path} />
          <Tile label="Load 1m" value={sys.host.load_avg["1m"].toFixed(2)} />
          <Tile label="Load 5m" value={sys.host.load_avg["5m"].toFixed(2)} />
          <Tile label="Load 15m" value={sys.host.load_avg["15m"].toFixed(2)} />
          <Tile
            label="Uptime"
            value={`${Math.floor(sys.host.uptime_seconds / 3600)}h`}
          />
        </div>
      )}
    </div>
  );
}
