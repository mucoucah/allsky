import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Satellite } from "lucide-react";
import { api, type SatPass } from "../../lib/api";
import { NumberField, ToggleField } from "../fields";

function fmtTime(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch { return iso.slice(11, 16); }
}

export function SatelliteSection() {
  const qc = useQueryClient();
  const { data: cfg } = useQuery({ queryKey: ["satCfg"], queryFn: api.satConfig });
  const update = useMutation({
    mutationFn: api.setSatConfig,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["satCfg"] }),
  });
  const scan = useMutation({ mutationFn: api.satScanNow });

  if (!cfg) return null;

  return (
    <section className="card">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
        <Satellite size={20} className="text-accent" />
        Satellite Pass Prediction
      </h2>
      <p className="text-xs text-ink-dim mb-3">
        Predicts visible satellite passes (ISS, Starlink, Hubble, etc.) using TLE data from CelesTrak.
        Alerts you before interesting passes so you can watch or capture them. No hardware or API key required.
      </p>
      <div className="flex flex-col gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={cfg.enabled}
            onChange={(e) => update.mutate({ enabled: e.target.checked })}
          />
          Enable satellite tracking
        </label>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <NumberField
            label="Poll interval (min)"
            value={cfg.poll_interval_minutes}
            onChange={(v) => update.mutate({ poll_interval_minutes: Math.max(v, 5) })}
          />
          <NumberField
            label="Predict hours ahead"
            value={cfg.hours_ahead}
            onChange={(v) => update.mutate({ hours_ahead: Math.min(v, 72) })}
          />
          <NumberField
            label="Min elevation (°)"
            value={cfg.min_elevation_deg}
            onChange={(v) => update.mutate({ min_elevation_deg: v })}
          />
          <NumberField
            label="Alert before (min)"
            value={cfg.alert_minutes_before}
            onChange={(v) => update.mutate({ alert_minutes_before: v })}
          />
        </div>

        {/* TLE groups */}
        <div className="border-t border-bg-raised pt-3 mt-1">
          <p className="text-xs text-ink-muted mb-2 font-medium">Satellite groups to track</p>
          <div className="flex flex-wrap gap-3">
            {(["stations", "visual", "starlink"] as const).map((g) => {
              const groups = cfg.tle_groups ?? [];
              const checked = groups.includes(g);
              const labels: Record<string, string> = {
                stations: "Space stations (ISS, Tiangong)",
                visual: "Bright satellites (Hubble, rocket bodies)",
                starlink: "Starlink constellation",
              };
              return (
                <label key={g} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      const next = checked ? groups.filter((x: string) => x !== g) : [...groups, g];
                      update.mutate({ tle_groups: next });
                    }}
                  />
                  {labels[g]}
                </label>
              );
            })}
          </div>
        </div>

        {/* Alert triggers */}
        <div className="border-t border-bg-raised pt-3 mt-1">
          <p className="text-xs text-ink-muted mb-2 font-medium">Alert triggers</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {([
              ["iss", "ISS passes", "Alert before International Space Station passes"],
              ["space_station", "Any space station", "ISS, Tiangong, CSS"],
              ["bright_passes", "Bright passes", "Any satellite reaching >45° elevation"],
              ["starlink", "Starlink satellites", "Alert for Starlink passes (can be very frequent)"],
              ["all_visible", "All visible passes", "Every sunlit satellite above min elevation"],
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
          <div className="grid grid-cols-2 gap-3 mt-3">
            <NumberField
              label="Alert min elevation (°)"
              value={cfg.alert_min_elevation_deg}
              onChange={(v) => update.mutate({ alert_min_elevation_deg: v })}
            />
            <NumberField
              label="Alert cooldown (min)"
              value={cfg.alert_cooldown_minutes}
              onChange={(v) => update.mutate({ alert_cooldown_minutes: Math.max(v, 1) })}
            />
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => scan.mutate()}
            disabled={scan.isPending}
            className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm inline-flex items-center gap-1.5"
          >
            <Satellite size={14} />
            {scan.isPending ? "Computing passes..." : "Scan now"}
          </button>
        </div>

        {scan.isSuccess && scan.data && (
          <div className="bg-bg-base rounded-lg border border-bg-raised p-3">
            {scan.data.overhead.length > 0 && (
              <div className="mb-3">
                <div className="text-sm font-medium text-accent mb-1">Currently overhead</div>
                <div className="flex flex-wrap gap-2">
                  {scan.data.overhead.map((s) => (
                    <span key={s.norad_id} className="px-2 py-0.5 bg-accent/10 text-accent rounded text-xs font-mono">
                      {s.name} {s.elevation_deg}° {s.is_sunlit ? "☀" : ""}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div className="text-sm font-medium mb-2">
              {scan.data.passes.length} upcoming passes (next {cfg.hours_ahead}h)
            </div>
            {scan.data.passes.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-ink-muted border-b border-bg-raised">
                      <th className="text-left py-1 pr-2">Satellite</th>
                      <th className="text-left py-1 pr-2">Rise</th>
                      <th className="text-right py-1 pr-2">Max°</th>
                      <th className="text-left py-1 pr-2">Set</th>
                      <th className="text-right py-1 pr-2">Duration</th>
                      <th className="text-left py-1">Visible</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scan.data.passes.slice(0, 20).map((p, i) => (
                      <tr key={`${p.norad_id}-${i}`} className="border-b border-bg-raised/50 hover:bg-bg-raised/30">
                        <td className="py-1.5 pr-2 font-mono font-medium">{p.name}</td>
                        <td className="py-1.5 pr-2 font-mono">{fmtTime(p.rise_time)}</td>
                        <td className="py-1.5 pr-2 text-right font-mono">{p.max_elev_deg}°</td>
                        <td className="py-1.5 pr-2 font-mono">{fmtTime(p.set_time)}</td>
                        <td className="py-1.5 pr-2 text-right font-mono">{p.duration_sec}s</td>
                        <td className="py-1.5">
                          {p.is_visible
                            ? <span className="text-emerald-400">☀ Yes</span>
                            : <span className="text-ink-dim">No</span>}
                        </td>
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
