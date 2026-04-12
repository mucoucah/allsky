import { useId } from "react";
import type { SettingDef } from "../lib/api";
import { fieldErrors } from "../lib/validate";

/** Upstream docs base — rewrites relative /documentation/ links to the
 *  original Allsky GitHub repository wiki/documentation. */
const DOCS_BASE = "https://htmlpreview.github.io/?https://github.com/thomasjacquin/allsky/blob/master";

/** Rewrite doc links in description HTML so they point to the upstream docs. */
function fixDocLinks(html: string): string {
  return html.replace(
    /href=["']\/documentation\//g,
    `href="${DOCS_BASE}/documentation/`,
  ).replace(
    /href=["']\/execute\.php[^"']*/g,
    'href="#',  // disable PHP execute links — not applicable
  ).replace(
    /<a\s+(?=[^>]*allsky=['"]true['"])/g,
    '<a target="_blank" rel="noopener noreferrer" ',
  );
}

interface Props {
  def: SettingDef;
  value: unknown;
  onChange: (next: unknown) => void;
  disabled?: boolean;
  dirty?: boolean;
}

/** Type-aware widget for a single Allsky setting.
 *
 *  Falls back to a plain text input for any type we don't recognise — that's
 *  intentional: a new upstream type should be displayable, just not editable
 *  with full fidelity until we add a widget for it. */
export function SettingField({ def, value, onChange, disabled, dirty }: Props) {
  const id = useId();
  const errors = fieldErrors(def, value);
  const borderClass =
    errors.length > 0 ? "border-err" : dirty ? "border-accent" : "border-bg-raised";
  const inputBase = `bg-bg-base border rounded px-2 py-0.5 text-sm font-mono disabled:opacity-50 ${borderClass}`;

  const hasDefault = def.default !== null && def.default !== undefined && def.default !== "";
  const isAtDefault = hasDefault && String(value) === String(def.default);

  // Size the input based on type.
  const isNumber = def.type === "integer" || def.type === "float" || def.type === "percent";
  const isBoolean = def.type === "boolean";
  const isWide = def.type === "widetext" || def.type === "text";
  const inputCls = isNumber
    ? `${inputBase} w-24`
    : isWide
    ? `${inputBase} w-full`
    : `${inputBase} w-48`;

  return (
    <div className="flex items-start gap-2 py-1.5">
      {/* Label column */}
      <label htmlFor={id} className="text-sm shrink-0 w-[200px] pt-0.5">
        <span className="text-ink font-medium">{def.label}</span>
        {def.action === "reload" && (
          <span className="ml-1 text-[9px] uppercase text-warn">restart</span>
        )}
        {dirty && <span className="ml-1 text-[10px] text-accent">&#9679;</span>}
        {def.description && (
          <div
            className="text-[11px] text-ink-dim mt-0.5 leading-tight [&_a]:text-accent [&_a]:underline"
            dangerouslySetInnerHTML={{ __html: fixDocLinks(def.description) }}
          />
        )}
      </label>

      {/* Input column */}
      <div className="flex items-center gap-2 flex-1 min-w-0">
        {renderWidget(def, value, onChange, disabled, id, inputCls)}
        {hasDefault && !isBoolean && (
          <button
            type="button"
            className={`text-[10px] shrink-0 font-mono ${
              isAtDefault ? "text-emerald-400" : "text-accent hover:underline"
            }`}
            title={isAtDefault ? "At default" : `Reset to ${def.default}`}
            onClick={() => { if (!isAtDefault && !disabled) onChange(def.default); }}
            disabled={disabled || isAtDefault}
          >
            {isAtDefault ? "\u2713" : `\u21ba${def.default}`}
          </button>
        )}
      </div>

      {/* Errors */}
      {errors.length > 0 && (
        <span className="text-[10px] text-err shrink-0">{errors.join(", ")}</span>
      )}
    </div>
  );
}

function renderWidget(
  def: SettingDef,
  value: unknown,
  onChange: (next: unknown) => void,
  disabled: boolean | undefined,
  id: string,
  cls: string,
) {
  // Boolean toggle
  if (def.type === "boolean") {
    const checked = value === true || value === "true";
    return (
      <button
        id={id}
        type="button"
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`flex items-center gap-2 text-sm w-fit ${disabled ? "opacity-50" : ""}`}
        aria-pressed={checked}
      >
        <span
          className={`w-9 h-5 rounded-full p-0.5 border transition-colors ${
            checked ? "bg-accent border-accent" : "bg-bg-base border-bg-raised"
          }`}
        >
          <span
            className={`block w-4 h-4 rounded-full bg-bg-base shadow transition-transform ${
              checked ? "translate-x-4 bg-bg-panel" : ""
            }`}
          />
        </span>
        <span className="text-ink-muted text-xs">{checked ? "on" : "off"}</span>
      </button>
    );
  }

  // Select dropdown (only when options are explicit objects — otherwise the
  // values are camera-driver placeholders that upstream resolves at install
  // time and we just show a number input for now).
  if (
    (def.type === "select" || def.type === "select_integer") &&
    Array.isArray(def.options) &&
    def.options.length > 0 &&
    typeof def.options[0] === "object"
  ) {
    const opts = def.options as Array<{ label: string; value: unknown }>;
    return (
      <select
        id={id}
        disabled={disabled}
        value={String(value ?? "")}
        onChange={(e) => {
          const raw = e.target.value;
          const numeric = def.type === "select_integer" ? parseInt(raw, 10) : raw;
          onChange(numeric);
        }}
        className={cls}
      >
        {opts.map((o) => (
          <option key={String(o.value)} value={String(o.value)}>
            {o.label}
          </option>
        ))}
      </select>
    );
  }

  // Numeric inputs
  if (def.type === "integer" || def.type === "float" || def.type === "percent") {
    return (
      <input
        id={id}
        type="number"
        disabled={disabled}
        step={def.type === "integer" ? 1 : "any"}
        min={numericish(def.minimum) ?? undefined}
        max={numericish(def.maximum) ?? undefined}
        value={value === undefined || value === null ? "" : String(value)}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === "") return onChange(null);
          const n = def.type === "integer" ? parseInt(raw, 10) : parseFloat(raw);
          onChange(Number.isFinite(n) ? n : raw);
        }}
        className={cls}
      />
    );
  }

  // Long text
  if (def.type === "widetext") {
    return (
      <textarea
        id={id}
        disabled={disabled}
        rows={2}
        value={value == null ? "" : String(value)}
        onChange={(e) => onChange(e.target.value)}
        className={`${cls} resize-y`}
      />
    );
  }

  // Default: text input
  return (
    <input
      id={id}
      type="text"
      disabled={disabled}
      value={value == null ? "" : String(value)}
      onChange={(e) => onChange(e.target.value)}
      className={cls}
    />
  );
}

function numericish(v: unknown): number | null {
  if (typeof v === "number") return v;
  if (typeof v === "string") {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}
