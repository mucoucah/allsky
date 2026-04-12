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
  const baseInput =
    "bg-bg-base border rounded-lg px-2 py-1 text-sm font-mono w-full disabled:opacity-50";
  const borderClass =
    errors.length > 0 ? "border-err" : dirty ? "border-accent" : "border-bg-raised";

  const hasDefault = def.default !== null && def.default !== undefined && def.default !== "";
  const isAtDefault = hasDefault && String(value) === String(def.default);

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="flex items-center justify-between gap-3">
        <span className="text-ink text-sm">
          {def.label}
          {def.action === "reload" && (
            <span
              className="ml-2 text-[10px] uppercase tracking-wide text-warn"
              title="Changing this restarts Allsky"
            >
              restart
            </span>
          )}
          {dirty && <span className="ml-2 text-[10px] text-accent">&#9679;</span>}
        </span>
      </label>

      {renderWidget(def, value, onChange, disabled, id, `${baseInput} ${borderClass}`)}

      {/* Default / recommended value */}
      {hasDefault && def.type !== "boolean" && (
        <div className="text-[11px] text-ink-dim flex items-center gap-1">
          <span>Default:</span>
          <button
            type="button"
            className={`font-mono px-1 rounded ${
              isAtDefault
                ? "text-emerald-400"
                : "text-accent hover:underline cursor-pointer"
            }`}
            title={isAtDefault ? "Currently at default" : "Click to reset to default"}
            onClick={() => { if (!isAtDefault && !disabled) onChange(def.default); }}
            disabled={disabled || isAtDefault}
          >
            {String(def.default)}
          </button>
          {isAtDefault && <span className="text-emerald-400 text-[10px]">&#10003;</span>}
        </div>
      )}

      {def.description && (
        <div
          className="text-xs text-ink-dim [&_a]:text-accent [&_a]:underline"
          dangerouslySetInnerHTML={{ __html: fixDocLinks(def.description) }}
        />
      )}
      {errors.length > 0 && (
        <div className="text-xs text-err">{errors.join(", ")}</div>
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
  if (def.type === "widetext" || def.type === "text") {
    return (
      <textarea
        id={id}
        disabled={disabled}
        rows={3}
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
