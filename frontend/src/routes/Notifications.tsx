import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell, Radar, Focus, Send, Plus, Trash2, TestTube2,
} from "lucide-react";
import { api, type NotifChannel } from "../lib/api";

export default function Notifications() {
  return (
    <div className="flex flex-col gap-6">
      <ChannelsSection />
      <ManualSendSection />
      <MeteorSection />
      <FocusSection />
      <RainSection />
    </div>
  );
}

// ── Channels ────────────────────────────────────────────────────

function ChannelsSection() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["channels"], queryFn: api.notifChannels });
  const del = useMutation({
    mutationFn: api.deleteChannel,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["channels"] }),
  });
  const test = useMutation({ mutationFn: api.testChannel });
  const [adding, setAdding] = useState(false);

  return (
    <section className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Bell size={20} /> Notification channels
        </h2>
        <button
          onClick={() => setAdding(true)}
          className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium inline-flex items-center gap-1.5"
        >
          <Plus size={16} /> Add channel
        </button>
      </div>

      {data?.channels.length ? (
        <ul className="divide-y divide-bg-raised text-sm">
          {data.channels.map((ch) => (
            <li key={ch.id} className="py-2 flex items-center gap-3">
              <span className={`pill ${ch.enabled ? "pill-ok" : "pill-warn"}`}>
                {ch.type}
              </span>
              <span className="font-mono">{ch.name || ch.id}</span>
              <span className="text-ink-dim text-xs ml-auto">
                {ch.enabled ? "enabled" : "disabled"}
              </span>
              <button
                onClick={() => test.mutate(ch.id)}
                disabled={test.isPending}
                className="text-xs px-2 py-1 rounded-lg border border-bg-raised text-ink-muted"
                title="Send a test notification"
              >
                <TestTube2 size={14} />
              </button>
              <button
                onClick={() => del.mutate(ch.id)}
                className="text-xs px-2 py-1 rounded-lg border border-bg-raised text-err"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-ink-dim text-sm">
          No channels configured. Add Telegram, Discord, Email, ntfy, or webhook.
        </div>
      )}

      {test.isSuccess && (
        <div className="text-xs text-ok mt-2">Test sent successfully.</div>
      )}
      {test.isError && (
        <div className="text-xs text-err mt-2">
          Test failed: {(test.error as Error).message}
        </div>
      )}

      {adding && <AddChannelForm onDone={() => { setAdding(false); qc.invalidateQueries({ queryKey: ["channels"] }); }} />}
    </section>
  );
}

const CHANNEL_TYPES = ["telegram", "discord", "email", "ntfy", "webhook"] as const;
const CHANNEL_FIELDS: Record<string, string[]> = {
  telegram: ["bot_token", "chat_id"],
  discord: ["webhook_url"],
  email: ["smtp_host", "smtp_port", "smtp_user", "smtp_pass", "smtp_tls", "from_addr", "to_addr"],
  ntfy: ["server", "topic", "auth", "priority"],
  webhook: ["url", "method"],
};

function AddChannelForm({ onDone }: { onDone: () => void }) {
  const [type, setType] = useState<string>("telegram");
  const [name, setName] = useState("");
  const [cfg, setCfg] = useState<Record<string, string>>({});
  const create = useMutation({
    mutationFn: api.createChannel,
    onSuccess: onDone,
  });

  return (
    <div className="mt-3 p-3 rounded-xl bg-bg-base border border-bg-raised flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <select
          className="bg-bg-panel border border-bg-raised rounded-lg px-2 py-1 text-sm"
          value={type}
          onChange={(e) => { setType(e.target.value); setCfg({}); }}
        >
          {CHANNEL_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <input
          className="bg-bg-panel border border-bg-raised rounded-lg px-2 py-1 text-sm flex-1"
          placeholder="Channel name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {(CHANNEL_FIELDS[type] || []).map((field) => (
          <label key={field} className="flex flex-col gap-0.5">
            <span className="text-xs text-ink-muted">{field}</span>
            <input
              className="bg-bg-panel border border-bg-raised rounded-lg px-2 py-1 text-sm font-mono"
              type={field.includes("pass") || field.includes("token") || field.includes("secret") ? "password" : "text"}
              value={cfg[field] || ""}
              onChange={(e) => setCfg({ ...cfg, [field]: e.target.value })}
            />
          </label>
        ))}
      </div>

      <div className="flex gap-2">
        <button
          onClick={() =>
            create.mutate({
              type,
              name: name || type,
              enabled: true,
              config: cfg,
              send_snapshot: true,
              send_timelapse: true,
            })
          }
          disabled={create.isPending}
          className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium disabled:opacity-50"
        >
          {create.isPending ? "Creating…" : "Create"}
        </button>
        <button
          onClick={onDone}
          className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── Manual send ─────────────────────────────────────────────────

function ManualSendSection() {
  const [subject, setSubject] = useState("Allsky observation");
  const [body, setBody] = useState("");
  const [snap, setSnap] = useState(true);
  const [tl, setTl] = useState(false);
  const send = useMutation({ mutationFn: api.manualSend });

  return (
    <section className="card">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
        <Send size={20} /> Send manually
      </h2>
      <div className="flex flex-col gap-2">
        <input
          className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="Subject"
        />
        <textarea
          className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm resize-y"
          rows={3}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Message body"
        />
        <div className="flex items-center gap-4 text-sm">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={snap} onChange={(e) => setSnap(e.target.checked)} />
            Include snapshot
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={tl} onChange={(e) => setTl(e.target.checked)} />
            Include timelapse
          </label>
          <button
            onClick={() => send.mutate({ subject, body, include_snapshot: snap, include_timelapse: tl })}
            disabled={send.isPending}
            className="ml-auto px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium disabled:opacity-50"
          >
            {send.isPending ? "Sending…" : "Send to all channels"}
          </button>
        </div>
        {send.isSuccess && (
          <div className="text-xs text-ok">
            Sent. Results: {JSON.stringify(send.data.results)}
          </div>
        )}
      </div>
    </section>
  );
}

// ── Meteor detection ────────────────────────────────────────────

function MeteorSection() {
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
        Runs Canny edge detection + Hough Line Transform on each captured frame.
        When bright linear streaks (meteors / falling stars) are found, sends an
        alert with the annotated image through your notification channels.
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
          label="Poll interval (min)"
          value={Number(d.poll_interval_minutes ?? 15)}
          onChange={(v) => setDraft({ ...d, poll_interval_minutes: v })}
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

// ── Focus monitoring ────────────────────────────────────────────

function FocusSection() {
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

// ── tiny helper widgets ─────────────────────────────────────────

function ToggleField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm cursor-pointer">
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  const [local, setLocal] = useState(() => String(value ?? ""));
  useEffect(() => {
    const parsed = parseFloat(local);
    if (!Number.isFinite(parsed) || parsed !== value) {
      setLocal(String(value ?? ""));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <label className="flex flex-col gap-0.5 text-sm">
      <span className="text-ink-muted text-xs">{label}</span>
      <input
        type="text"
        inputMode="decimal"
        value={local}
        onChange={(e) => {
          const raw = e.target.value;
          if (!/^-?\d*\.?\d*$/.test(raw)) return;
          setLocal(raw);
          const n = parseFloat(raw);
          if (Number.isFinite(n)) onChange(n);
        }}
        className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 font-mono text-sm w-full"
      />
    </label>
  );
}


// ── Rain Detection ─────────────────────────────────────────────

function RainSection() {
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
