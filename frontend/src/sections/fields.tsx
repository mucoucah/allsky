import { useEffect, useState } from "react";

export function ToggleField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm cursor-pointer">
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

export function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  const [local, setLocal] = useState(() => String(value ?? ""));
  useEffect(() => {
    const parsed = parseFloat(local);
    if (!Number.isFinite(parsed) || parsed !== value) {
      setLocal(String(value ?? ""));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <label className="flex flex-col gap-0.5 text-sm">
      <span className="text-ink-muted text-xs">{label}</span>
      <input
        type="text"
        inputMode="decimal"
        value={local}
        onChange={(e) => {
          const raw = e.target.value;
          if (!/^-?\d*\.?\d*$/.test(raw)) return;
          setLocal(raw);
          const n = parseFloat(raw);
          if (Number.isFinite(n)) onChange(n);
        }}
        className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 font-mono text-sm w-full"
      />
    </label>
  );
}
