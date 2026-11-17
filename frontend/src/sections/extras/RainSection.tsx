import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { NumberField } from "../fields";

export function RainSection() {
  const qc = useQueryClient();
  const { data: cfg } = useQuery({ queryKey: ["rainCfg"], queryFn: api.rainConfig });
  const update = useMutation({
    mutationFn: api.setRainConfig,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rainCfg"] }),
  });
  const detect = useMutation({ mutationFn: api.detectRainNow });

  if (!cfg) return null;

  return (
    <section className="card">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
        Rain / Moisture Detection
      </h2>
      <p className="text-xs text-ink-dim mb-3">
        Detects water droplets on the camera dome by analyzing bright blobs,
        contrast reduction, and texture patterns. Sends an alert when rain is detected.
      </p>
      <div className="flex flex-col gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={cfg.enabled}
            onChange={(e) => update.mutate({ enabled: e.target.checked })}
          />
          Enable rain detection
        </label>
        <div className="grid grid-cols-2 gap-3">
          <NumberField
            label="Poll interval (minutes)"
            value={cfg.poll_interval_minutes}
            onChange={(v) => update.mutate({ poll_interval_minutes: v })}
          />
          <NumberField
            label="Confidence threshold (0-1)"
            value={cfg.confidence_threshold}
            onChange={(v) => update.mutate({ confidence_threshold: v })}
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={cfg.include_snapshot}
            onChange={(e) => update.mutate({ include_snapshot: e.target.checked })}
          />
          Include snapshot in alert
        </label>
        <div className="flex gap-2">
          <button
            onClick={() => detect.mutate()}
            disabled={detect.isPending}
            className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm inline-flex items-center gap-1.5"
          >
            {detect.isPending ? "Detecting..." : "Test now"}
          </button>
        </div>
        {detect.isSuccess && detect.data && (
          <div className={`text-sm p-2 rounded-lg ${detect.data.rain_detected ? "bg-amber-500/10 text-amber-400" : "bg-emerald-500/10 text-emerald-400"}`}>
            {detect.data.rain_detected
              ? `Rain detected! Confidence: ${(detect.data.confidence * 100).toFixed(0)}% — ${detect.data.message}`
              : `Clear — confidence: ${(detect.data.confidence * 100).toFixed(0)}%, ${detect.data.message}`}
          </div>
        )}
      </div>
    </section>
  );
}
