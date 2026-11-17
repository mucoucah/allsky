import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes } from "lucide-react";
import { api } from "../lib/api";
import { ChannelsSection } from "../sections/extras/ChannelsSection";
import { ManualSendSection } from "../sections/extras/ManualSendSection";
import { RainSection } from "../sections/extras/RainSection";
import { AdsbSection } from "../sections/extras/AdsbSection";
import { SatelliteSection } from "../sections/extras/SatelliteSection";
import { UploadSection } from "../sections/extras/UploadSection";

export default function Extras() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["alerts"], queryFn: api.alerts });
  const ack = useMutation({
    mutationFn: api.ackAlert,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Boxes size={22} className="text-accent" />
        <h1 className="text-xl font-semibold">Extras</h1>
      </div>
      <p className="text-sm text-ink-dim -mt-2">
        ADS-B, satellites, rain, notification channels, and website upload. Meteor hits live under Tonight.
      </p>
      <div id="rain"><RainSection /></div>
      <AdsbSection />
      <SatelliteSection />
      <ChannelsSection />
      <ManualSendSection />
      <UploadSection />
      <section className="card" id="alerts">
        <h2 className="text-lg font-semibold mb-3">Alert history</h2>
        {data?.length ? (
          <ul className="divide-y divide-bg-raised text-sm">
            {data.map((a) => (
              <li key={a.id} className="py-2 flex items-start gap-3">
                <span className={`pill mt-0.5 ${a.level === "error" ? "pill-err" : a.level === "warning" ? "pill-warn" : "pill-ok"}`}>
                  {a.level}
                </span>
                <div className="flex-1">
                  <div className="text-xs text-ink-dim font-mono">
                    {new Date(a.created_at * 1000).toLocaleString()} · {a.source}
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
          <div className="text-ink-dim text-sm">No alerts.</div>
        )}
      </section>
    </div>
  );
}
