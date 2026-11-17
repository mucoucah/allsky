import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plane, Radar } from "lucide-react";
import { api, type AircraftInfo } from "../../lib/api";
import { callsignLookup } from "../../lib/callsigns";
import { NumberField, ToggleField } from "../fields";

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

export function AdsbSection() {
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
                      <th className="text-left py-1 pr-2">Callsign</th>
                      <th className="text-left py-1 pr-2">Operator</th>
                      <th className="text-left py-1 pr-2">Type</th>
                      <th className="text-left py-1 pr-2">Reg</th>
                      <th className="text-right py-1 pr-2">Alt</th>
                      <th className="text-right py-1 pr-2">V/S</th>
                      <th className="text-right py-1 pr-2">Speed</th>
                      <th className="text-right py-1 pr-2">Dist</th>
                      <th className="text-right py-1 pr-2">Bearing</th>
                      <th className="text-left py-1 pr-2">Src</th>
                      <th className="text-left py-1">Cat</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scan.data.aircraft.map((ac) => (
                      <tr key={ac.icao24} className="border-b border-bg-raised/50 hover:bg-bg-raised/30">
                        <td className="py-1.5 pr-2 font-mono font-medium">
                          {ac.callsign || ac.icao24}
                          {ac.squawk && ["7500", "7600", "7700"].includes(ac.squawk) && (
                            <span className="ml-1 text-red-400 font-bold">SQ{ac.squawk}</span>
                          )}
                          {ac.spi && <span className="ml-1 text-amber-400" title="Special Position Identification">SPI</span>}
                        </td>
                        <td className="py-1.5 pr-2 text-ink-muted">
                          {ac.operator || (ac.callsign ? callsignLookup(ac.callsign) ?? "" : "")}
                        </td>
                        <td className="py-1.5 pr-2 font-mono">{ac.aircraft_type || ""}</td>
                        <td className="py-1.5 pr-2 font-mono text-ink-dim">{ac.registration || ""}</td>
                        <td className="py-1.5 pr-2 text-right font-mono">{fmtAlt(ac.altitude_m)}</td>
                        <td className="py-1.5 pr-2 text-right font-mono">
                          {ac.vertical_rate != null ? (
                            <span className={ac.vertical_rate > 1 ? "text-emerald-400" : ac.vertical_rate < -1 ? "text-amber-400" : ""}>
                              {ac.vertical_rate > 1 ? "▲" : ac.vertical_rate < -1 ? "▼" : "—"}{" "}
                              {Math.abs(Math.round(ac.vertical_rate * 196.85))}
                            </span>
                          ) : "—"}
                        </td>
                        <td className="py-1.5 pr-2 text-right font-mono">{fmtSpeed(ac.velocity_mps)}</td>
                        <td className="py-1.5 pr-2 text-right font-mono">{ac.distance_km} km</td>
                        <td className="py-1.5 pr-2 text-right font-mono">
                          {ac.bearing_deg}° {bearingLabel(ac.bearing_deg)}
                        </td>
                        <td className="py-1.5 pr-2">
                          {ac.position_source && (
                            <span className={`px-1 rounded text-[10px] ${ac.position_source === "ADS-B" ? "bg-emerald-500/20 text-emerald-400" : "bg-amber-500/20 text-amber-400"}`}>
                              {ac.position_source}
                            </span>
                          )}
                        </td>
                        <td className="py-1.5 text-ink-dim text-[10px]">{ac.category || ""}</td>
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


