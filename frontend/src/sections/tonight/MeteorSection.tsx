import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Radar } from "lucide-react";
import { api } from "../../lib/api";
import { NumberField, ToggleField } from "../fields";

export function MeteorSection() {
  const qc = useQueryClient();
  const { data: cfg } = useQuery({ queryKey: ["meteorCfg"], queryFn: api.meteorConfig });
  const save = useMutation({
    mutationFn: api.setMeteorConfig,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meteorCfg"] }),
  });
  const detectNow = useMutation({ mutationFn: api.detectMeteorNow });
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);

  const d = draft ?? cfg ?? {};

  return (
    <section className="card">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-1">
        <Radar size={20} /> Meteor / streak detection
      </h2>
      <p className="text-xs text-ink-dim mb-3">
        On each new night frame: grayscale, half size, mask, then subtract the
        previous frames so stars and streaks that last more than one exposure
        are dropped. Hits are saved under html/allsky/meteors/. Alerts are
        rate-limited.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <ToggleField
          label="Enabled"
          value={Boolean(d.enabled)}
          onChange={(v) => setDraft({ ...d, enabled: v })}
        />
        <NumberField
          label="Min streak length (px)"
          value={Number(d.min_streak_length ?? 100)}
          onChange={(v) => setDraft({ ...d, min_streak_length: v })}
        />
        <NumberField
          label="Alert cooldown (min)"
          value={Number(d.alert_cooldown_minutes ?? 10)}
          onChange={(v) => setDraft({ ...d, alert_cooldown_minutes: v })}
        />
        <ToggleField
          label="Include timelapse"
          value={Boolean(d.include_timelapse)}
          onChange={(v) => setDraft({ ...d, include_timelapse: v })}
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
          onClick={() => detectNow.mutate()}
          disabled={detectNow.isPending}
          className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm"
        >
          {detectNow.isPending ? "Detecting…" : "Run detection now"}
        </button>
        {save.isSuccess && <span className="text-xs text-ok">Saved</span>}
      </div>

      {detectNow.data && (
        <div className="mt-2 text-sm">
          Result:{" "}
          <span className={detectNow.data.meteor_count > 0 ? "text-ok font-bold" : "text-ink-muted"}>
            {detectNow.data.meteor_count} meteor(s), {detectNow.data.line_count} line(s)
          </span>
        </div>
      )}
    </section>
  );
}
