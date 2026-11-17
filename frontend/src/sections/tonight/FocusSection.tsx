import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Focus } from "lucide-react";
import { api } from "../../lib/api";
import { NumberField, ToggleField } from "../fields";

export function FocusSection() {
  const qc = useQueryClient();
  const { data: cfg } = useQuery({ queryKey: ["focusCfg"], queryFn: api.focusConfig });
  const { data: current } = useQuery({
    queryKey: ["focusCurrent"],
    queryFn: api.currentFocus,
    refetchInterval: 10_000,
  });
  const save = useMutation({
    mutationFn: api.setFocusConfig,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["focusCfg"] }),
  });
  const calibrate = useMutation({
    mutationFn: api.calibrateFocus,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["focusCfg"] });
      qc.invalidateQueries({ queryKey: ["focusCurrent"] });
    },
  });
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);

  const d = draft ?? cfg ?? {};

  return (
    <section className="card">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-1">
        <Focus size={20} /> Focus quality monitor
      </h2>
      <p className="text-xs text-ink-dim mb-3">
        Computes a sharpness score (variance of Laplacian) on each frame.
        Alerts if the score stays below a calibrated baseline for several
        consecutive checks — prevents false alarms from passing clouds.
      </p>

      {/* Live score */}
      {current && (
        <div className="flex items-center gap-4 mb-3 text-sm">
          <span className="text-ink-muted">Current score</span>
          <span className="font-mono text-lg">
            {current.score != null ? current.score.toFixed(1) : "—"}
          </span>
          <span
            className={`pill ${
              current.status === "ok"
                ? "pill-ok"
                : current.status === "soft"
                ? "pill-err"
                : "pill-warn"
            }`}
          >
            {current.status}
          </span>
          {current.baseline != null && (
            <span className="text-ink-dim text-xs">
              baseline {current.baseline.toFixed(1)} · threshold{" "}
              {current.threshold?.toFixed(1) ?? "—"}
            </span>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <ToggleField
          label="Enabled"
          value={Boolean(d.enabled)}
          onChange={(v) => setDraft({ ...d, enabled: v })}
        />
        <NumberField
          label="Threshold (%)"
          value={Number(d.threshold_pct ?? 60)}
          onChange={(v) => setDraft({ ...d, threshold_pct: v })}
        />
        <NumberField
          label="Consecutive fails"
          value={Number(d.consecutive_failures_to_alert ?? 5)}
          onChange={(v) => setDraft({ ...d, consecutive_failures_to_alert: v })}
        />
        <NumberField
          label="Poll interval (min)"
          value={Number(d.poll_interval_minutes ?? 5)}
          onChange={(v) => setDraft({ ...d, poll_interval_minutes: v })}
        />
      </div>

      <div className="flex items-center gap-2 mt-3">
        <button
          onClick={() => save.mutate(d)}
          disabled={!draft || save.isPending}
          className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save config"}
        </button>
        <button
          onClick={() => calibrate.mutate()}
          disabled={calibrate.isPending}
          className="px-3 py-1.5 rounded-lg border border-accent text-accent text-sm"
        >
          {calibrate.isPending ? "Calibrating…" : "Set current as in-focus baseline"}
        </button>
        {calibrate.isSuccess && (
          <span className="text-xs text-ok">
            Baseline set to {calibrate.data.baseline_sharpness}
          </span>
        )}
        {save.isSuccess && <span className="text-xs text-ok">Saved</span>}
      </div>
    </section>
  );
}
