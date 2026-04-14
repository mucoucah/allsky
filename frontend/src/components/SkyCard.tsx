import { Sun, Moon } from "lucide-react";
import type { SystemSnapshot } from "../lib/api";

interface Props {
  time: NonNullable<SystemSnapshot["host"]["time"]>;
}

/** Visual celestial dashboard: sun position, phase/illumination of moon,
 *  day/night status, next rise/set, current time + timezone. */
export function SkyCard({ time }: Props) {
  const isDay = time.is_day;
  const sunEl = time.sun_elevation_deg;
  const sunAz = time.sun_azimuth_deg;

  // Format next events.
  const fmtEvent = (iso?: string) => {
    if (!iso) return "—";
    const d = new Date(iso);
    const now = new Date();
    const diffMs = d.getTime() - now.getTime();
    const diffHours = diffMs / 1000 / 3600;
    if (diffHours < 0) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (diffHours < 24) {
      return `${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} (in ${diffHours.toFixed(1)}h)`;
    }
    return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };

  return (
    <section className={`card ${isDay ? "bg-gradient-to-br from-amber-500/10 to-transparent border-amber-500/30" : "bg-gradient-to-br from-indigo-500/10 to-transparent border-indigo-500/30"}`}>
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-base font-semibold flex items-center gap-2">
          {isDay ? (
            <><Sun size={16} className="text-amber-400" /> Daytime</>
          ) : (
            <><Moon size={16} className="text-indigo-300" /> Nighttime</>
          )}
        </h2>
        <div className="text-[9px] uppercase tracking-wide text-ink-muted">
          {isDay ? "DAY" : "NIGHT"} settings
        </div>
      </div>

      {/* Compact visual + data */}
      <div className="flex items-start gap-3">
        <CelestialVisual
          sunElevation={sunEl}
          moonIllum={time.moon?.illumination_pct}
          isDay={isDay ?? false}
          moonVisible={time.moon?.is_visible ?? false}
        />
        <div className="flex-1 text-[11px] space-y-0.5">
          {sunEl !== undefined && (
            <div className="flex justify-between">
              <span className="text-ink-muted">Sun</span>
              <span className="font-mono">
                {sunEl.toFixed(1)}&deg;
                {sunAz !== undefined && (
                  <span className="text-ink-dim"> @ {sunAz.toFixed(0)}&deg;</span>
                )}
              </span>
            </div>
          )}
          {time.moon && (
            <div className="flex justify-between">
              <span className="text-ink-muted">Moon</span>
              <span className="font-mono">
                {time.moon.phase_name.replace(/^(Waxing |Waning )/, "")}, {time.moon.illumination_pct.toFixed(0)}%
              </span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-ink-muted">{isDay ? "Sunset" : "Sunrise"}</span>
            <span className="font-mono">
              {fmtEvent(isDay ? time.next_sunset_local : time.next_sunrise_local)}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-ink-muted">Time</span>
            <span className="font-mono text-[10px]">
              {new Date(time.system_time).toLocaleTimeString([], {
                hour: "2-digit", minute: "2-digit",
              })}{" "}
              <span className="text-ink-dim">{time.timezone_name?.split("/")[1] ?? time.timezone_name ?? ""}</span>
            </span>
          </div>
          {time.day_night_angle !== undefined && (
            <div className="flex justify-between">
              <span className="text-ink-muted">Threshold</span>
              <span className="font-mono text-ink-dim">{time.day_night_angle}&deg;</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/** Simple SVG showing sun arc + moon phase. */
function CelestialVisual({
  sunElevation, moonIllum, isDay, moonVisible,
}: {
  sunElevation?: number;
  moonIllum?: number;
  isDay: boolean;
  moonVisible: boolean;
}) {
  // Sun position on a 180° arc (horizon to zenith to horizon).
  // We map elevation -90..+90 to a half-circle.
  const el = sunElevation ?? 0;
  const clamped = Math.max(-30, Math.min(90, el));
  const angleRad = (clamped / 90) * (Math.PI / 2);
  const cx = 50;
  const cy = 55;
  const r = 40;
  const sunX = cx + r * Math.cos(Math.PI - angleRad);
  const sunY = cy - r * Math.sin(angleRad);

  // Moon phase: fraction 0..1 of illuminated fraction drawn as a waning curve.
  const illum = (moonIllum ?? 0) / 100;

  return (
    <div className="w-16 h-14 relative shrink-0">
      <svg viewBox="0 0 100 70" className="w-full h-full">
        {/* Horizon line */}
        <line x1="5" y1={cy} x2="95" y2={cy} stroke="currentColor" strokeOpacity="0.2" />
        {/* Sun arc path */}
        <path d={`M 10 ${cy} A 40 40 0 0 1 90 ${cy}`}
              fill="none" stroke="currentColor" strokeOpacity="0.15" strokeDasharray="2 3" />
        {/* Sun */}
        {isDay && el > -30 && (
          <circle cx={sunX} cy={sunY} r="6" fill="#fbbf24" stroke="#f59e0b" strokeWidth="0.5" />
        )}
        {/* Moon with simple phase representation */}
        {!isDay && (
          <g>
            <circle cx={50} cy={25} r="10" fill="#1e293b" stroke="#94a3b8" strokeWidth="0.5" />
            {/* Illuminated part: right crescent if waxing, left if waning — simplified */}
            <clipPath id="moon-clip">
              <circle cx={50} cy={25} r="10" />
            </clipPath>
            <ellipse
              cx={50 + (illum - 0.5) * 20}
              cy={25}
              rx={10 * Math.abs(0.5 - illum) * 2 + 1}
              ry={10}
              fill="#e2e8f0"
              clipPath="url(#moon-clip)"
            />
          </g>
        )}
      </svg>
      {moonVisible && !isDay && (
        <Moon size={12} className="absolute top-0 right-0 text-indigo-300" />
      )}
    </div>
  );
}
