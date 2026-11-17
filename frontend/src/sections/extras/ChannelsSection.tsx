import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Plus, TestTube2, Trash2 } from "lucide-react";
import { api } from "../../lib/api";

export function ChannelsSection() {
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
