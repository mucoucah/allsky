import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type OffloadConfig, type PiHeartbeatStatus } from "../lib/api";
import { usePollInterval } from "../hooks/usePollInterval";
import { fmtBytes } from "../lib/format";

export function PiHeartbeat() {
  const poll = usePollInterval(15_000);
  const { data } = useQuery({
    queryKey: ["offload-pi"],
    queryFn: api.offloadPi,
    refetchInterval: poll,
  });
  const status: PiHeartbeatStatus | null = data?.status ?? null;
  if (!status) {
    return (
      <section className="card flex flex-col gap-2">
        <h2 className="text-lg font-semibold">Pi</h2>
        <p className="text-sm text-ink-dim">
          {data?.message ?? "Waiting for a heartbeat from the Pi."}
        </p>
      </section>
    );
  }
  const throttle = status.throttled;
  const hot = throttle?.throttled_now || throttle?.soft_temp_limit_now || status.thermal_state === "stopped";
  return (
    <section className="card flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Pi</h2>
        <span className={`pill ${hot ? "pill-err" : "pill-ok"}`}>
          {status.thermal_state ?? "Pi"}
        </span>
      </div>
      <p className="text-[10px] text-ink-dim -mt-1">Values below come from the Pi heartbeat.</p>
      <Row label="Pi host" value={status.hostname ?? "—"} />
      <Row label="Pi CPU" value={status.temp_c == null ? "—" : `${status.temp_c.toFixed(1)} °C`} />
      <Row label="Pi throttle" value={throttle?.raw ?? "—"} />
      <Row label="Pi disk free" value={status.disk ? fmtBytes(status.disk.free) : "—"} />
      <Row
        label="Pi outbox"
        value={`${status.outbox_files ?? 0} files, ${fmtBytes(status.outbox_bytes ?? 0)}`}
      />
      <Row label="Pi last frame" value={status.last_frame_time ?? "—"} />
      {status.camera_error && (
        <p className="text-xs text-err break-words">{status.camera_error}</p>
      )}
      <p className="text-[10px] text-ink-dim">
        Heartbeat {status.timestamp}. Live meteor alerts need the PC on.
      </p>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-ink-muted">{label}</span>
      <span className="font-mono text-xs text-right">{value}</span>
    </div>
  );
}

const EMPTY: OffloadConfig = {
  mode: "normal",
  jpeg_quality: 90,
  outbox_dir: "/var/lib/allsky/outbox",
  outbox_max_bytes: 4 * 1024 * 1024 * 1024,
  drop_day_frames: false,
  night_priority: true,
  remote: {
    host: "",
    port: 2222,
    user: "",
    path: "/srv/allsky/incoming",
    ssh_key: "",
    bandwidth_limit_kbps: 0,
    settings_path: "/srv/allsky/to-pi",
    status_name: "status/pi-status.json",
  },
  processor: {
    incoming_dir: "/srv/allsky/incoming",
    data_dir: "/srv/allsky/data",
    to_pi_dir: "/srv/allsky/to-pi",
    retention_days: 14,
    raw_retention_days: 14,
    min_free_gb: 10,
    max_disk_bytes: 0,
    encoder: "auto",
    meteor_scale: 1.0,
    use_cuda: "auto",
    min_streak_length: 100,
    poll_seconds: 2,
    quiet_with_day_seconds: 300,
    quiet_alone_seconds: 2700,
  },
};

function useOffloadDraft() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["offload"], queryFn: api.offload });
  const [draft, setDraft] = useState<OffloadConfig>(EMPTY);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (data) setDraft(data);
  }, [data]);

  const save = useMutation({
    mutationFn: api.saveOffload,
    onSuccess: () => {
      setMsg("Saved. The Pi pulls this on its next sync.");
      qc.invalidateQueries({ queryKey: ["offload"] });
    },
    onError: (err: Error) => setMsg(err.message),
  });

  return { draft, setDraft, save, msg };
}

export function CaptureSettings() {
  const { draft, setDraft, save, msg } = useOffloadDraft();

  function setRemote(key: keyof OffloadConfig["remote"], value: string | number) {
    setDraft((prev) => ({ ...prev, remote: { ...prev.remote, [key]: value } }));
  }

  return (
    <section className="card flex flex-col gap-3">
      <div>
        <h2 className="text-lg font-semibold">Capture</h2>
        <p className="text-xs text-ink-dim mt-1">
          These numbers are copied to the Pi. JPEG quality, day-frame dropping, and night
          priority decide what the Pi sends. Host, SSH key, and processor paths are on System.
        </p>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        Mode
        <select
          className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1"
          value={draft.mode}
          onChange={(e) => setDraft({ ...draft, mode: e.target.value as OffloadConfig["mode"] })}
        >
          <option value="normal">normal</option>
          <option value="capture-only">capture-only</option>
        </select>
      </label>
      <div className="grid md:grid-cols-2 gap-3">
        <Field label="JPEG quality" value={draft.jpeg_quality} onChange={(v) => setDraft({ ...draft, jpeg_quality: Number(v) })} />
        <Field label="Bandwidth limit (kbps, 0 = none)" value={draft.remote.bandwidth_limit_kbps} onChange={(v) => setRemote("bandwidth_limit_kbps", Number(v))} />
        <Field label="Outbox max bytes" value={draft.outbox_max_bytes} onChange={(v) => setDraft({ ...draft, outbox_max_bytes: Number(v) })} />
        <Field label="Outbox directory (on the Pi)" value={draft.outbox_dir} onChange={(v) => setDraft({ ...draft, outbox_dir: v })} />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={draft.drop_day_frames}
          onChange={(e) => setDraft({ ...draft, drop_day_frames: e.target.checked })}
        />
        Drop day frames on the Pi
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={draft.night_priority}
          onChange={(e) => setDraft({ ...draft, night_priority: e.target.checked })}
        />
        Send night frames before day frames
      </label>
      <SaveRow pending={save.isPending} msg={msg} onSave={() => save.mutate(draft)} />
    </section>
  );
}

export function ProcessorSettings() {
  const { draft, setDraft, save, msg } = useOffloadDraft();

  function setRemote(key: keyof OffloadConfig["remote"], value: string | number) {
    setDraft((prev) => ({ ...prev, remote: { ...prev.remote, [key]: value } }));
  }
  function setProcessor(key: keyof OffloadConfig["processor"], value: string | number) {
    setDraft((prev) => ({ ...prev, processor: { ...prev.processor, [key]: value } }));
  }

  return (
    <section className="card flex flex-col gap-3">
      <div>
        <h2 className="text-lg font-semibold">PC processor</h2>
        <p className="text-xs text-ink-dim mt-1">
          Where the Pi uploads frames and where this PC writes products. Capture-only on the Pi
          skips overlays, ImageMagick, and end-of-night products. Raw frame retention deletes
          capture JPEGs older than that many days and keeps timelapse, keogram, startrails,
          and meteor hits. The disk guard is shown on the PC card.
        </p>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <Field label="PC host" value={draft.remote.host} onChange={(v) => setRemote("host", v)} />
        <Field label="SSH port" value={draft.remote.port} onChange={(v) => setRemote("port", Number(v))} />
        <Field label="SSH user" value={draft.remote.user} onChange={(v) => setRemote("user", v)} />
        <Field label="SSH key on the Pi" value={draft.remote.ssh_key} onChange={(v) => setRemote("ssh_key", v)} />
        <Field label="Incoming path" value={draft.remote.path} onChange={(v) => setRemote("path", v)} />
        <Field label="Settings path the Pi pulls" value={draft.remote.settings_path} onChange={(v) => setRemote("settings_path", v)} />
        <Field label="Processor incoming dir" value={draft.processor.incoming_dir} onChange={(v) => setProcessor("incoming_dir", v)} />
        <Field label="Processor data dir" value={draft.processor.data_dir} onChange={(v) => setProcessor("data_dir", v)} />
        <Field label="Raw frame retention days" value={draft.processor.raw_retention_days ?? 14} onChange={(v) => setProcessor("raw_retention_days", Number(v))} />
        <Field label="Low-disk guard (GB free)" value={draft.processor.min_free_gb ?? 10} onChange={(v) => setProcessor("min_free_gb", Number(v))} />
        <Field label="Disk budget bytes (0 = days only)" value={draft.processor.max_disk_bytes} onChange={(v) => setProcessor("max_disk_bytes", Number(v))} />
        <label className="flex flex-col gap-1 text-sm">
          Encoder
          <select
            className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1"
            value={draft.processor.encoder}
            onChange={(e) => setProcessor("encoder", e.target.value)}
          >
            <option value="auto">auto</option>
            <option value="h264_nvenc">h264_nvenc</option>
            <option value="hevc_nvenc">hevc_nvenc</option>
            <option value="libx264">libx264</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          CUDA
          <select
            className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1"
            value={draft.processor.use_cuda}
            onChange={(e) => setProcessor("use_cuda", e.target.value)}
          >
            <option value="auto">auto</option>
            <option value="on">on</option>
            <option value="off">off</option>
          </select>
        </label>
      </div>
      <SaveRow pending={save.isPending} msg={msg} onSave={() => save.mutate(draft)} />
    </section>
  );
}

function SaveRow({ pending, msg, onSave }: { pending: boolean; msg: string | null; onSave: () => void }) {
  return (
    <div className="flex items-center gap-3">
      <button
        className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium disabled:opacity-50"
        disabled={pending}
        onClick={onSave}
      >
        Save offload config
      </button>
      {msg && <span className="text-xs text-ink-muted">{msg}</span>}
    </div>
  );
}

function Field({
  label, value, onChange,
}: {
  label: string;
  value: string | number;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      {label}
      <input
        className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 font-mono text-xs"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
