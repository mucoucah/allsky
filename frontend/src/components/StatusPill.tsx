interface Props { status: string }

/** Maps free-form Allsky status strings to a coloured pill. */
export function StatusPill({ status }: Props) {
  const lower = status.toLowerCase();
  let cls = "pill-warn";
  if (lower.includes("running")) cls = "pill-ok";
  else if (lower.includes("error") || lower.includes("not running") || lower.includes("stopped")) cls = "pill-err";
  return <span className={`pill ${cls}`}>{status}</span>;
}
