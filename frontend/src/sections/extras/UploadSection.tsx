import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { api } from "../../lib/api";

export function UploadSection() {
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
          {test.data.ok ? "Upload test succeeded!" : (test.data.error || "Upload test failed.")}
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
