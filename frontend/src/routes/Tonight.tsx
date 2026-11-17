import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoonStar } from "lucide-react";
import { api } from "../lib/api";
import { MeteorHits } from "../sections/tonight/MeteorHits";
import { MeteorSection } from "../sections/tonight/MeteorSection";
import { FocusSection } from "../sections/tonight/FocusSection";

export default function Tonight() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["alerts"], queryFn: api.alerts });
  const ack = useMutation({
    mutationFn: api.ackAlert,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const meteorAlerts = useMemo(
    () => (data ?? []).filter((a) => a.source === "meteor"),
    [data],
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <MoonStar size={22} className="text-accent" />
        <h1 className="text-xl font-semibold">Tonight</h1>
      </div>
      <MeteorHits />
      <MeteorSection />
      <FocusSection />
      <section className="card">
        <h2 className="text-lg font-semibold mb-3">Meteor alerts</h2>
        {meteorAlerts.length ? (
          <ul className="divide-y divide-bg-raised text-sm">
            {meteorAlerts.map((a) => (
              <li key={a.id} className="py-2 flex items-start gap-3">
                <span className="pill pill-ok mt-0.5">{a.level}</span>
                <div className="flex-1">
                  <div className="text-xs text-ink-dim font-mono">
                    {new Date(a.created_at * 1000).toLocaleString()}
                  </div>
                  <div>{a.message}</div>
                </div>
                {!a.acknowledged_at && (
                  <button className="text-xs px-2 py-1 rounded-lg border border-bg-raised" onClick={() => ack.mutate(a.id)}>
                    ack
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-ink-dim text-sm">No meteor alerts yet.</div>
        )}
      </section>
    </div>
  );
}
