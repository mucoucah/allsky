/** Evaluate Allsky's `booldependson` expressions against current values.
 *
 *  Upstream syntax (seen in options.json) is one of:
 *    - "settingname"
 *    - "settingname AND othername"
 *    - "settingname AND othername AND third"
 *    - "settingname OR othername"
 *
 *  Each name resolves to a truthy boolean lookup against the values map.
 *  AND binds tighter than OR (matching the upstream PHP evaluator). */
export function evaluateDepends(
  expr: string | null | undefined,
  values: Record<string, unknown>,
): boolean {
  if (!expr) return true;
  const orParts = expr.split(/\s+OR\s+/i);
  return orParts.some((orPart) => {
    const andParts = orPart.split(/\s+AND\s+/i);
    return andParts.every((name) => {
      const v = values[name.trim()];
      return Boolean(v);
    });
  });
}
