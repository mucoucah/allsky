import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell, Radar, Focus, Send, Plus, Trash2, TestTube2, Plane,
} from "lucide-react";
import { api, type NotifChannel, type AircraftInfo } from "../lib/api";

export default function Notifications() {
  return (
    <div className="flex flex-col gap-6">
      <ChannelsSection />
      <ManualSendSection />
      <MeteorSection />
      <FocusSection />
      <RainSection />
      <AdsbSection />
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


// ── ADS-B Aircraft Tracking ───────────────────────────────────

function airlineFromCallsign(callsign: string): string | null {
  const prefix = callsign.slice(0, 3).toUpperCase();
  const airlines: Record<string, string> = {
    AAL: "American", UAL: "United", DAL: "Delta", SWA: "Southwest",
    JBU: "JetBlue", ASA: "Alaska", NKS: "Spirit", FFT: "Frontier",
    SKW: "SkyWest", RPA: "Republic", ENY: "Envoy", BAW: "British Airways",
    DLH: "Lufthansa", AFR: "Air France", KLM: "KLM", EZY: "easyJet",
    RYR: "Ryanair", UAE: "Emirates", QTR: "Qatar", SIA: "Singapore",
    ANA: "ANA", JAL: "JAL", CPA: "Cathay Pacific", QFA: "Qantas",
    THY: "Turkish", TAP: "TAP", IBE: "Iberia", ACA: "Air Canada",
    AZA: "ITA Airways", CSN: "China Southern", CCA: "Air China",
    CES: "China Eastern", EVA: "EVA Air", CAL: "China Airlines",
    KAL: "Korean Air", AAR: "Asiana", FDX: "FedEx", UPS: "UPS",
  };
  return airlines[prefix] ?? null;
}

function fmtAlt(m: number | null): string {
  if (m == null) return "—";
  const ft = Math.round(m * 3.281);
  return `${ft.toLocaleString()} ft`;
}

function fmtSpeed(mps: number | null): string {
  if (mps == null) return "—";
  return `${Math.round(mps * 1.944)} kts`;
}

function bearingLabel(deg: number): string {
  const dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return dirs[Math.round(deg / 45) % 8];
}

function AdsbSection() {
  const qc = useQueryClient();
  const { data: cfg } = useQuery({ queryKey: ["adsbCfg"], queryFn: api.adsbConfig });
  const update = useMutation({
    mutationFn: api.setAdsbConfig,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["adsbCfg"] }),
  });
  const scan = useMutation({ mutationFn: api.adsbScanNow });

  if (!cfg) return null;

  return (
    <section className="card">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
        <Plane size={20} className="text-accent" />
        ADS-B Aircraft Tracking
      </h2>
      <p className="text-xs text-ink-dim mb-3">
        Tracks aircraft near your camera using the OpenSky Network API. Shows nearby flights on the Dashboard
        and alerts on emergency squawk codes (7500/7600/7700). No hardware required — data is pulled from the internet.
      </p>
      <div className="flex flex-col gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={cfg.enabled}
            onChange={(e) => update.mutate({ enabled: e.target.checked })}
          />
          Enable aircraft tracking
        </label>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <NumberField
            label="Radius (km)"
            value={cfg.radius_km}
            onChange={(v) => update.mutate({ radius_km: v })}
          />
          <NumberField
            label={`Poll interval (sec) — min ${cfg.opensky_username ? "3" : "6"}`}
            value={cfg.poll_interval_seconds}
            onChange={(v) => {
              const min = cfg.opensky_username ? 3 : 6;
              update.mutate({ poll_interval_seconds: Math.max(v, min) });
            }}
          />
          <NumberField
            label="Min altitude (m)"
            value={cfg.min_altitude_m}
            onChange={(v) => update.mutate({ min_altitude_m: v })}
          />
          <NumberField
            label="Max on overlay"
            value={cfg.overlay_max_aircraft}
            onChange={(v) => update.mutate({ overlay_max_aircraft: v })}
          />
        </div>

        {/* Alert triggers */}
        <div className="border-t border-bg-raised pt-3 mt-1">
          <p className="text-xs text-ink-muted mb-2 font-medium">Alert triggers</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {([
              ["emergency_squawk", "Emergency squawk", "7500 hijack, 7600 radio failure, 7700 emergency"],
              ["all_flights", "All flights", "Any aircraft within radius"],
              ["low_altitude", "Low-altitude flights", `Below ${cfg.alert_low_altitude_ft ?? 3000} ft`],
              ["slow_mover", "Slow / hovering", `Below ${cfg.alert_slow_speed_kts ?? 100} kts — helicopters, drones`],
              ["no_callsign", "No-callsign flights", "Often military or government aircraft"],
            ] as const).map(([key, label, hint]) => {
              const triggers = cfg.alert_triggers ?? [];
              const checked = triggers.includes(key);
              return (
                <label key={key} className="flex items-start gap-2 text-sm p-2 rounded-lg bg-bg-base border border-bg-raised hover:border-accent/30 transition-colors cursor-pointer">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      const next = checked
                        ? triggers.filter((t: string) => t !== key)
                        : [...triggers, key];
                      update.mutate({ alert_triggers: next });
                    }}
                    className="mt-0.5"
                  />
                  <div>
                    <div className="font-medium">{label}</div>
                    <div className="text-xs text-ink-dim">{hint}</div>
                  </div>
                </label>
              );
            })}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
            <NumberField
              label="Low altitude threshold (ft)"
              value={cfg.alert_low_altitude_ft}
              onChange={(v) => update.mutate({ alert_low_altitude_ft: v })}
            />
            <NumberField
              label="Slow speed threshold (kts)"
              value={cfg.alert_slow_speed_kts}
              onChange={(v) => update.mutate({ alert_slow_speed_kts: v })}
            />
            <NumberField
              label="Alert cooldown (min)"
              value={cfg.alert_cooldown_minutes}
              onChange={(v) => update.mutate({ alert_cooldown_minutes: Math.max(v, 1) })}
            />
          </div>
        </div>

        {/* Display options */}
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={cfg.show_on_overlay}
              onChange={(e) => update.mutate({ show_on_overlay: e.target.checked })}
            />
            Show on image overlay
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={cfg.include_snapshot}
              onChange={(e) => update.mutate({ include_snapshot: e.target.checked })}
            />
            Include snapshot in alerts
          </label>
        </div>

        <div className="border-t border-bg-raised pt-3 mt-1">
          <p className="text-xs text-ink-dim mb-2">
            <strong>OpenSky credentials</strong> (optional — anonymous: ~10 req/min, registered: ~100 req/min).
            Register free at opensky-network.org.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-0.5 text-sm">
              <span className="text-ink-muted text-xs">Username</span>
              <input
                type="text"
                value={cfg.opensky_username}
                onChange={(e) => update.mutate({ opensky_username: e.target.value })}
                placeholder="(anonymous)"
                className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 font-mono text-sm"
              />
            </label>
            <label className="flex flex-col gap-0.5 text-sm">
              <span className="text-ink-muted text-xs">Password</span>
              <input
                type="password"
                value={cfg.opensky_password}
                onChange={(e) => update.mutate({ opensky_password: e.target.value })}
                placeholder="****"
                className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 font-mono text-sm"
              />
            </label>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => scan.mutate()}
            disabled={scan.isPending}
            className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm inline-flex items-center gap-1.5"
          >
            <Radar size={14} />
            {scan.isPending ? "Scanning..." : "Scan now"}
          </button>
        </div>

        {scan.isSuccess && scan.data && (
          <div className="bg-bg-base rounded-lg border border-bg-raised p-3">
            <div className="text-sm font-medium mb-2">
              {scan.data.count} aircraft found
            </div>
            {scan.data.count > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-ink-muted border-b border-bg-raised">
                      <th className="text-left py-1 pr-3">Callsign</th>
                      <th className="text-left py-1 pr-3">Airline</th>
                      <th className="text-right py-1 pr-3">Altitude</th>
                      <th className="text-right py-1 pr-3">Speed</th>
                      <th className="text-right py-1 pr-3">Distance</th>
                      <th className="text-right py-1 pr-3">Bearing</th>
                      <th className="text-right py-1 pr-3">Elev</th>
                      <th className="text-left py-1">Country</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scan.data.aircraft.map((ac) => (
                      <tr key={ac.icao24} className="border-b border-bg-raised/50 hover:bg-bg-raised/30">
                        <td className="py-1.5 pr-3 font-mono font-medium">
                          {ac.callsign || ac.icao24}
                          {ac.squawk && ["7500", "7600", "7700"].includes(ac.squawk) && (
                            <span className="ml-1 text-red-400 font-bold">SQ{ac.squawk}</span>
                          )}
                        </td>
                        <td className="py-1.5 pr-3 text-ink-muted">
                          {ac.callsign ? airlineFromCallsign(ac.callsign) ?? "" : ""}
                        </td>
                        <td className="py-1.5 pr-3 text-right font-mono">{fmtAlt(ac.altitude_m)}</td>
                        <td className="py-1.5 pr-3 text-right font-mono">{fmtSpeed(ac.velocity_mps)}</td>
                        <td className="py-1.5 pr-3 text-right font-mono">{ac.distance_km} km</td>
                        <td className="py-1.5 pr-3 text-right font-mono">
                          {ac.bearing_deg}° {bearingLabel(ac.bearing_deg)}
                        </td>
                        <td className="py-1.5 pr-3 text-right font-mono">{ac.elevation_deg}°</td>
                        <td className="py-1.5 text-ink-muted">{ac.origin_country}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
