import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Moon, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import { fmtBytes } from "../../lib/format";

export function DarksSection() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["darks"], queryFn: api.listDarks });
  const capture = useMutation({
    mutationFn: api.captureDark,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["darks"] }),
  });
  const del = useMutation({
    mutationFn: api.deleteDark,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["darks"] }),
  });

  return (
    <section className="card">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <Moon size={20} /> Dark Frames
      </h2>
      <p className="text-xs text-ink-dim mb-3">
        Dark frames are captured with the lens capped — used to subtract thermal noise from images.
        Point the camera at a dark scene or cover the dome, then click "Capture darks".
        Remember to disable dark capture (via Settings) when finished and enable dark subtraction.
      </p>
      <div className="flex items-center gap-3 mb-3">
        <button
          onClick={() => capture.mutate()}
          disabled={capture.isPending}
          className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium inline-flex items-center gap-1.5"
        >
          <Camera size={14} />
          {capture.isPending ? "Starting..." : "Capture darks"}
        </button>
        <span className="text-xs text-ink-muted">
          {data?.darks.length ?? 0} darks · {fmtBytes(data?.total_bytes ?? 0)}
        </span>
      </div>
      {capture.data?.message && (
        <div className="text-xs text-ok mb-2">{capture.data.message}</div>
      )}
      {data && data.darks.length > 0 && (
        <div className="divide-y divide-bg-raised text-sm">
          {data.darks.map((d) => (
            <div key={d.name} className="py-2 flex items-center gap-3">
              <span className="font-mono flex-1">{d.name}</span>
              {d.temperature_c != null && (
                <span className="text-ink-muted">{d.temperature_c.toFixed(1)}°C</span>
              )}
              <span className="text-ink-muted text-xs">{fmtBytes(d.size_bytes)}</span>
              <button
                onClick={() => del.mutate(d.name)}
                className="p-1 text-err hover:bg-err/10 rounded"
                title="Delete"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      {data && data.darks.length === 0 && (
        <div className="text-ink-dim text-sm py-2">No dark frames captured yet.</div>
      )}
    </section>
  );
}
