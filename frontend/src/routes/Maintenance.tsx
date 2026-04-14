import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  RefreshCw, Download, Trash2, Camera, Upload, Calendar, Package, Moon,
} from "lucide-react";
import { api } from "../lib/api";

export default function Maintenance() {
  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      <h1 className="text-xl font-semibold">Maintenance</h1>
      <UpdateSection />
      <DarksSection />
      <GenerateForDateSection />
      <UploadSection />
    </div>
  );
}

/* ── Update check ─────────────────────────────────────────────── */

function UpdateSection() {
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
        To update the Web UI: SSH into the Pi and run <code className="text-accent">cd ~/allsky &amp;&amp; git pull &amp;&amp; sudo ./install.sh</code>
      </p>
    </section>
  );
}

/* ── Dark frames ──────────────────────────────────────────────── */

function DarksSection() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["darks"], queryFn: api.listDarks });
  const capture = useMutation({
    mutationFn: api.captureDark,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["darks"] }),
  });
  const del = useMutation({
    mutationFn: api.deleteDark,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["darks"] }),
  });

  const fmtBytes = (n: number) => {
    const units = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
  };

  return (
    <section className="card">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <Moon size={20} /> Dark Frames
      </h2>
      <p className="text-xs text-ink-dim mb-3">
        Dark frames are captured with the lens capped — used to subtract thermal noise from images.
        Point the camera at a dark scene or cover the dome, then click "Capture darks".
        Remember to disable dark capture (via Settings) when finished and enable dark subtraction.
      </p>
      <div className="flex items-center gap-3 mb-3">
        <button
          onClick={() => capture.mutate()}
          disabled={capture.isPending}
          className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium inline-flex items-center gap-1.5"
        >
          <Camera size={14} />
          {capture.isPending ? "Starting..." : "Capture darks"}
        </button>
        <span className="text-xs text-ink-muted">
          {data?.darks.length ?? 0} darks · {fmtBytes(data?.total_bytes ?? 0)}
        </span>
      </div>
      {capture.data?.message && (
        <div className="text-xs text-ok mb-2">{capture.data.message}</div>
      )}
      {data && data.darks.length > 0 && (
        <div className="divide-y divide-bg-raised text-sm">
          {data.darks.map((d) => (
            <div key={d.name} className="py-2 flex items-center gap-3">
              <span className="font-mono flex-1">{d.name}</span>
              {d.temperature_c != null && (
                <span className="text-ink-muted">{d.temperature_c.toFixed(1)}°C</span>
              )}
              <span className="text-ink-muted text-xs">{fmtBytes(d.size_bytes)}</span>
              <button
                onClick={() => del.mutate(d.name)}
                className="p-1 text-err hover:bg-err/10 rounded"
                title="Delete"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      {data && data.darks.length === 0 && (
        <div className="text-ink-dim text-sm py-2">No dark frames captured yet.</div>
      )}
    </section>
  );
}

/* ── Generate for past date ────────────────────────────────────── */

function GenerateForDateSection() {
  const { data: dates } = useQuery({
    queryKey: ["available-dates"],
    queryFn: api.availableDates,
  });
  const [selectedDate, setSelectedDate] = useState("");
  const [kinds, setKinds] = useState<Record<string, boolean>>({
    keogram: true,
    startrails: true,
    timelapse: true,
  });

  const generate = useMutation({
    mutationFn: () => {
      const selected = Object.entries(kinds).filter(([, v]) => v).map(([k]) => k);
      return api.generateForDate(selectedDate, selected);
    },
  });

  return (
    <section className="card">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <Calendar size={20} /> Regenerate for past date
      </h2>
      <p className="text-xs text-ink-dim mb-3">
        Re-create keogram, startrails, or timelapse for a specific night. Useful after fixing settings
        or if the automatic end-of-night run failed.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-ink-muted">Date</label>
          <select
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1.5 text-sm font-mono min-w-[200px]"
          >
            <option value="">Select a date...</option>
            {dates?.dates.map((d: any) => (
              <option key={d.date} value={d.date}>
                {d.date} ({d.image_count} images)
              </option>
            ))}
          </select>
        </div>
        {(["keogram", "startrails", "timelapse"] as const).map((k) => (
          <label key={k} className="flex items-center gap-1.5 text-sm capitalize">
            <input
              type="checkbox"
              checked={kinds[k]}
              onChange={(e) => setKinds({ ...kinds, [k]: e.target.checked })}
            />
            {k}
          </label>
        ))}
        <button
          onClick={() => generate.mutate()}
          disabled={!selectedDate || generate.isPending || !Object.values(kinds).some((v) => v)}
          className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium disabled:opacity-50"
        >
          {generate.isPending ? "Generating (can take minutes)..." : "Generate"}
        </button>
      </div>
      {generate.data && (
        <div className={`mt-3 p-2 rounded-lg text-xs ${generate.data.ok ? "bg-ok/10 text-ok" : "bg-err/10 text-err"}`}>
          {generate.data.ok ? "Completed successfully." : generate.data.error || "Failed."}
          {generate.data.output && (
            <pre className="mt-2 text-ink-muted whitespace-pre-wrap max-h-40 overflow-auto">
              {generate.data.output}
            </pre>
          )}
        </div>
      )}
    </section>
  );
}

/* ── Upload / Remote Website ──────────────────────────────────── */

function UploadSection() {
  const [type, setType] = useState<"local-web" | "remote-web" | "remote-server">("remote-web");
  const [cfg, setCfg] = useState<Record<string, string>>({});
  const test = useMutation({ mutationFn: (body: any) => api.testUpload(body) });

  const fields: Record<string, string[]> = {
    "remote-web": ["REMOTEWEBSITE_PROTOCOL", "REMOTEWEBSITE_HOST", "REMOTEWEBSITE_USER", "REMOTEWEBSITE_PASSWORD", "REMOTEWEBSITE_IMAGE_DIR"],
    "remote-server": ["REMOTESERVER_PROTOCOL", "REMOTESERVER_HOST", "REMOTESERVER_USER", "REMOTESERVER_PASSWORD", "REMOTESERVER_IMAGE_DIR"],
    "local-web": ["LOCAL_WEBSITE_DIR"],
  };

  return (
    <section className="card">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <Upload size={20} /> Upload / Remote Website
      </h2>
      <p className="text-xs text-ink-dim mb-3">
        Configure uploading images, keograms, startrails, and timelapses to a remote website or server.
        Supports FTP, SFTP, FTPS. Detailed upload settings are in the Settings page under "Website".
      </p>
      <div className="flex gap-2 mb-3">
        {(["local-web", "remote-web", "remote-server"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setType(t)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
              type === t ? "bg-accent/20 text-accent border border-accent/40" : "bg-bg-raised text-ink-muted"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        {fields[type].map((f) => (
          <label key={f} className="flex flex-col gap-1 text-xs">
            <span className="text-ink-muted">{f}</span>
            <input
              type={f.toLowerCase().includes("password") ? "password" : "text"}
              value={cfg[f] || ""}
              onChange={(e) => setCfg({ ...cfg, [f]: e.target.value })}
              className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 font-mono text-sm"
            />
          </label>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => test.mutate({ type, ...cfg })}
          disabled={test.isPending}
          className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium"
        >
          {test.isPending ? "Testing..." : "Test upload"}
        </button>
      </div>
      {test.data && (
        <div className={`mt-3 p-2 rounded-lg text-xs ${test.data.ok ? "bg-ok/10 text-ok" : "bg-err/10 text-err"}`}>
          {test.data.ok ? "Upload test successful!" : (test.data.error || "Upload test failed.")}
          {test.data.output && (
            <pre className="mt-2 text-ink-muted whitespace-pre-wrap max-h-40 overflow-auto">
              {test.data.output}
            </pre>
          )}
        </div>
      )}
    </section>
  );
}
