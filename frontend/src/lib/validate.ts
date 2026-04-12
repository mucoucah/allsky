/** Mirrors backend validation so we can show errors inline before save. */
import type { SettingDef } from "./api";

export function fieldErrors(def: SettingDef, value: unknown): string[] {
  const errs: string[] = [];
  if (def.type === "boolean") {
    // Accept actual booleans and string booleans (upstream stores "true"/"false").
    if (typeof value !== "boolean" && typeof value !== "string") errs.push("must be a boolean");
    return errs;
  }
  if (def.type === "integer") {
    if (typeof value !== "number" || !Number.isInteger(value)) errs.push("must be an integer");
  }
  if (def.type === "float" || def.type === "percent") {
    if (typeof value !== "number" || Number.isNaN(value)) errs.push("must be a number");
  }
  if (typeof value === "number") {
    const min = numericish(def.minimum);
    const max = numericish(def.maximum);
    if (min != null && value < min) errs.push(`min ${min}`);
    if (max != null && value > max) errs.push(`max ${max}`);
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
