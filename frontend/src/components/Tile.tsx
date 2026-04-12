import { ReactNode } from "react";

interface Props {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  status?: "ok" | "warn" | "err";
}

export function Tile({ label, value, hint, status }: Props) {
  return (
    <div className="tile">
      <div className="flex items-center justify-between">
        <div className="tile-label">{label}</div>
        {status && (
          <div className={`pill pill-${status}`}>
            {status === "ok" ? "OK" : status === "warn" ? "WARN" : "ERR"}
          </div>
        )}
      </div>
      <div className="tile-value">{value}</div>
      {hint && <div className="text-xs text-ink-dim">{hint}</div>}
    </div>
  );
}
