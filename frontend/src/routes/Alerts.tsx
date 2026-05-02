import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { api } from "../lib/api";
import { ChannelsSection, ManualSendSection } from "./Notifications";

export default function Alerts() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["alerts"], queryFn: api.alerts });
  const ack = useMutation({
    mutationFn: api.ackAlert,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Bell size={22} className="text-accent" />
        <h1 className="text-xl font-semibold">Alerts & Notifications</h1>
      </div>

      <ChannelsSection />
      <ManualSendSection />

      <section className="card">
        <h2 className="text-lg font-semibold mb-3">Alert History</h2>
        {data?.length ? (
          <ul className="divide-y divide-bg-raised text-sm">
            {data.map((a) => (
              <li key={a.id} className="py-2 flex items-start gap-3">
                <span
                  className={`pill mt-0.5 ${
                    a.level === "error"
                      ? "pill-err"
                      : a.level === "warning"
                      ? "pill-warn"
                      : "pill-ok"
                  }`}
                >
                  {a.level}
                </span>
                <div className="flex-1">
                  <div className="text-xs text-ink-dim font-mono">
                    {new Date(a.created_at * 1000).toLocaleString()} · {a.source}
                  </div>
                  <div>{a.message}</div>
                </div>
                {!a.acknowledged_at && (
                  <button
                    className="text-xs px-2 py-1 rounded-lg border border-bg-raised text-ink-muted"
                    onClick={() => ack.mutate(a.id)}
                  >
                    ack
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-ink-dim text-sm">No alerts.</div>
        )}
      </section>
    </div>
  );
}
