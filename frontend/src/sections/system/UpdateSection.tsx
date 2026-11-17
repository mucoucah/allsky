import { useQuery } from "@tanstack/react-query";
import { Package, RefreshCw } from "lucide-react";
import { api } from "../../lib/api";

export function UpdateSection() {
  const { data, refetch, isFetching } = useQuery({
    queryKey: ["check-update"],
    queryFn: api.checkUpdate,
  });

  return (
    <section className="card">
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <Package size={20} /> Updates
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Allsky Camera */}
        <div className="p-3 rounded-lg bg-bg-base border border-bg-raised">
          <div className="text-xs text-ink-muted mb-1">Allsky Camera</div>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm">Installed: <span className="font-mono">{data?.installed ?? "…"}</span></div>
              <div className="text-sm">Latest: <span className="font-mono">{data?.latest ?? "…"}</span></div>
            </div>
            {data?.update_available ? (
              <span className="pill pill-warn">update</span>
            ) : data?.installed ? (
              <span className="pill pill-ok">up to date</span>
            ) : null}
          </div>
        </div>

        {/* Web UI */}
        <div className="p-3 rounded-lg bg-bg-base border border-bg-raised">
          <div className="text-xs text-ink-muted mb-1">Web UI</div>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm">Installed: <span className="font-mono">v{data?.web_version ?? "…"}</span></div>
              <div className="text-sm">Latest: <span className="font-mono">v{data?.web_latest ?? "…"}</span></div>
            </div>
            {data?.web_update_available ? (
              <span className="pill pill-warn">update</span>
            ) : data?.web_version ? (
              <span className="pill pill-ok">up to date</span>
            ) : null}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 mt-3">
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm inline-flex items-center gap-1.5"
        >
          <RefreshCw size={14} className={isFetching ? "animate-spin" : ""} />
          {isFetching ? "Checking..." : "Check now"}
        </button>
        {data?.error && (
          <span className="text-xs text-err">{data.error}</span>
        )}
      </div>
      <p className="text-xs text-ink-dim mt-2">
        To update the web UI on this PC, from the repo run <code className="text-accent">cd ~/allsky &amp;&amp; git pull &amp;&amp; sudo ./install.sh</code>
      </p>
    </section>
  );
}
