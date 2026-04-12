import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type SettingDef } from "../lib/api";
import { evaluateDepends } from "../lib/depends";
import { fieldErrors } from "../lib/validate";
import { SettingField } from "../components/SettingField";

/** Editable, schema-driven settings UI.
 *
 *  - Loads schema (grouped by tab → section) and current values once.
 *  - Tracks a draft mirror of the values; the diff is what we PATCH.
 *  - Per-field disable based on `booldependson` (recomputed against the *draft*
 *    so toggling a parent immediately greys out its dependents).
 *  - Save sends only the diff to the backend, which validates again and shells
 *    out to upstream's makeChanges.sh for application. */
export default function Settings() {
  const qc = useQueryClient();
  const { data: schema, error: schemaErr, isError: schemaFailed } = useQuery({
    queryKey: ["schema"], queryFn: api.settingsSchema, retry: 2,
  });
  const { data: values, error: valuesErr, isError: valuesFailed } = useQuery({
    queryKey: ["values"], queryFn: api.settingsValues, retry: 2,
  });
  const { data: audit } = useQuery({ queryKey: ["audit"], queryFn: api.settingsAudit });

  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [tab, setTab] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // Seed draft from server values once they arrive.
  useEffect(() => {
    if (values) setDraft({ ...values });
  }, [values]);

  const tabs = useMemo(() => Object.keys(schema ?? {}), [schema]);
  const activeTab = tab ?? tabs[0] ?? null;

  const dirty = useMemo(() => {
    if (!values) return {};
    const d: Record<string, unknown> = {};
    for (const k of Object.keys(draft)) {
      if (JSON.stringify(draft[k]) !== JSON.stringify(values[k])) d[k] = draft[k];
    }
    return d;
  }, [draft, values]);
  const dirtyCount = Object.keys(dirty).length;

  // Aggregate validation errors so the save button can be disabled.
  const validationErrors = useMemo(() => {
    if (!schema) return [] as string[];
    const errs: string[] = [];
    for (const sections of Object.values(schema)) {
      for (const defs of Object.values(sections)) {
        for (const def of defs) {
          if (!(def.name in dirty)) continue;
          const e = fieldErrors(def, dirty[def.name]);
          for (const m of e) errs.push(`${def.label}: ${m}`);
        }
      }
    }
    return errs;
  }, [schema, dirty]);

  const save = useMutation({
    mutationFn: () => api.patchSettings(dirty),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["values"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
      setMsg(`Saved ${dirtyCount} change${dirtyCount === 1 ? "" : "s"}.`);
    },
    onError: (e: Error) => setMsg(`Failed: ${e.message}`),
  });

  function reset() {
    if (values) setDraft({ ...values });
    setMsg(null);
  }

  if (schemaFailed || valuesFailed) {
    return (
      <div className="card text-err">
        <h2 className="text-lg font-semibold mb-2">Settings failed to load</h2>
        {schemaErr && <p className="text-sm mb-1">Schema: {String(schemaErr)}</p>}
        {valuesErr && <p className="text-sm mb-1">Values: {String(valuesErr)}</p>}
        <p className="text-xs text-ink-muted mt-2">
          Check the System page log viewer for backend errors.
          The options.json file may be missing or unreadable.
        </p>
        <a href="/api/settings/debug" target="_blank" rel="noreferrer"
          className="text-xs text-accent underline mt-2 inline-block">
          Open debug info
        </a>
      </div>
    );
  }
  if (!schema || !values) return <div className="text-ink-dim">loading schema…</div>;

  const lower = search.trim().toLowerCase();
  const sections = (activeTab && schema[activeTab]) || {};

  return (
    <div className="flex flex-col gap-4">
      {/* Sticky toolbar */}
      <div className="card sticky top-14 z-10 flex flex-wrap items-center gap-3">
        <input
          type="search"
          placeholder="Search settings…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm w-56"
        />
        <label className="flex items-center gap-1 text-xs text-ink-muted">
          <input
            type="checkbox"
            checked={showAdvanced}
            onChange={(e) => setShowAdvanced(e.target.checked)}
          />
          show advanced
        </label>
        <div className="ml-auto flex items-center gap-2">
          {dirtyCount > 0 && (
            <span className="text-xs text-accent">{dirtyCount} unsaved</span>
          )}
          {validationErrors.length > 0 && (
            <span
              className="text-xs text-err"
              title={validationErrors.join("\n")}
            >
              {validationErrors.length} error{validationErrors.length === 1 ? "" : "s"}
            </span>
          )}
          <button
            disabled={dirtyCount === 0 || save.isPending}
            onClick={reset}
            className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm disabled:opacity-50"
          >
            Reset
          </button>
          <button
            disabled={
              dirtyCount === 0 || save.isPending || validationErrors.length > 0
            }
            onClick={() => save.mutate()}
            className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium disabled:opacity-50"
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </div>
        {msg && <div className="basis-full text-xs text-ink-dim">{msg}</div>}
      </div>

      {/* Tabs */}
      <div className="card flex flex-wrap gap-1">
        {tabs.map((t) => {
          const tDirty = countTabDirty(schema[t], dirty);
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`nav-link flex items-center gap-2 ${activeTab === t ? "active" : ""}`}
            >
              {t}
              {tDirty > 0 && (
                <span className="text-[10px] bg-accent text-bg-base rounded-full px-1.5">
                  {tDirty}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Sections */}
      <div className="flex flex-col gap-4">
        {Object.entries(sections).map(([sectionName, defs]) => {
          const filtered = defs.filter((def) => {
            if (!showAdvanced && def.advanced) return false;
            if (!lower) return true;
            return (
              def.name.toLowerCase().includes(lower) ||
              def.label.toLowerCase().includes(lower) ||
              (def.description || "").toLowerCase().includes(lower)
            );
          });
          if (filtered.length === 0) return null;
          return (
            <section key={sectionName} className="card">
              {sectionName && (
                <h3 className="text-sm uppercase tracking-wide text-ink-muted mb-3">
                  {sectionName}
                </h3>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
                {filtered.map((def) => (
                  <SettingField
                    key={def.name}
                    def={def}
                    value={draft[def.name]}
                    dirty={def.name in dirty}
                    disabled={!evaluateDepends(def.depends_on, draft)}
                    onChange={(next) =>
                      setDraft((cur) => ({ ...cur, [def.name]: next }))
                    }
                  />
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {/* Audit log */}
      {audit && audit.length > 0 && (
        <section className="card">
          <h3 className="text-sm uppercase tracking-wide text-ink-muted mb-2">
            Recent changes
          </h3>
          <ul className="text-xs font-mono divide-y divide-bg-raised">
            {audit.map((a) => (
              <li key={a.id} className="py-1.5 flex items-baseline gap-3">
                <span className="text-ink-dim">
                  {new Date(a.ts * 1000).toLocaleString()}
                </span>
                <span className="text-ink">{a.key}</span>
                <span className="text-ink-muted">
                  {a.old_value ?? "—"} → {a.new_value ?? "—"}
                </span>
                {a.actor && <span className="ml-auto text-ink-dim">{a.actor}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function countTabDirty(
  sections: Record<string, SettingDef[]>,
  dirty: Record<string, unknown>,
): number {
  let n = 0;
  for (const defs of Object.values(sections)) {
    for (const def of defs) if (def.name in dirty) n++;
  }
  return n;
}
