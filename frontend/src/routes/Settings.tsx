import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

/** Read-only settings browser for M1.
 *  M3 will replace this with an editable, validated form that PATCHes back. */
export default function Settings() {
  const { data: schema } = useQuery({ queryKey: ["schema"], queryFn: api.settingsSchema });
  const { data: values } = useQuery({ queryKey: ["values"], queryFn: api.settingsValues });

  const tabs = useMemo(() => Object.keys(schema ?? {}), [schema]);
  const [tab, setTab] = useState<string | null>(null);
  const activeTab = tab ?? tabs[0] ?? null;

  if (!schema || !values) return <div className="text-ink-dim">loading schema…</div>;

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-wrap gap-1">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`nav-link ${activeTab === t ? "active" : ""}`}
          >
            {t}
          </button>
        ))}
      </div>

      {activeTab && schema[activeTab] && (
        <div className="flex flex-col gap-4">
          {Object.entries(schema[activeTab]).map(([section, entries]) => (
            <section key={section} className="card">
              {section && (
                <h3 className="text-sm uppercase tracking-wide text-ink-muted mb-2">
                  {section}
                </h3>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 text-sm">
                {entries.map((e) => (
                  <div key={e.name} className="flex flex-col">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-ink">{e.label}</span>
                      <span className="font-mono text-ink-muted text-right break-all">
                        {formatValue(values[e.name])}
                      </span>
                    </div>
                    {e.description && (
                      <div
                        className="text-xs text-ink-dim"
                        dangerouslySetInnerHTML={{ __html: e.description }}
                      />
                    )}
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <div className="text-xs text-ink-dim">
        Read-only view (M1). Editable form with validation lands in M3.
      </div>
    </div>
  );
}

function formatValue(v: unknown): string {
  if (v === undefined || v === null || v === "") return "—";
  if (typeof v === "boolean") return v ? "on" : "off";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
