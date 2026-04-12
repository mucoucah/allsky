/** Mirrors backend validation so we can show errors inline before save. */
import type { SettingDef } from "./api";

export function fieldErrors(def: SettingDef, value: unknown): string[] {
  const errs: string[] = [];
  if (value === null || value === undefined || value === "") return errs;

  if (def.type === "boolean") {
    if (typeof value !== "boolean" && typeof value !== "string") errs.push("must be a boolean");
    return errs;
  }
  if (def.type === "integer") {
    const n = typeof value === "string" ? parseInt(value, 10) : value;
    if (typeof n !== "number" || !Number.isFinite(n) || !Number.isInteger(n)) {
      errs.push("must be an integer");
    }
  }
  if (def.type === "float" || def.type === "percent") {
    const n = typeof value === "string" ? parseFloat(value as string) : value;
    if (typeof n !== "number" || !Number.isFinite(n)) {
      errs.push("must be a number");
    }
  }
  // Range checks.
  const numVal = typeof value === "number" ? value : typeof value === "string" ? parseFloat(value) : NaN;
  if (Number.isFinite(numVal)) {
    const min = numericish(def.minimum);
    const max = numericish(def.maximum);
    if (min != null && numVal < min) errs.push(`min ${min}`);
    if (max != null && numVal > max) errs.push(`max ${max}`);
  }
  return errs;
}

function numericish(v: unknown): number | null {
  if (typeof v === "number") return v;
  if (typeof v === "string") {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}
