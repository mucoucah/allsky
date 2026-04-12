/** Tiny typed fetch client. Keeps API surface in one place so refactors are
 *  obvious. All endpoints are served under /api by FastAPI. */

const base = "/api";

async function request<T>(
  path: string,
  init?: RequestInit & { json?: unknown },
): Promise<T> {
  const opts: RequestInit = { ...init, headers: { ...(init?.headers || {}) } };
  if (init?.json !== undefined) {
    opts.body = JSON.stringify(init.json);
    (opts.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await fetch(`${base}${path}`, opts);
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try { detail = await res.json(); } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.blob()) as unknown as T;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`HTTP ${status}: ${JSON.stringify(detail)}`);
  }
}

// --- types (kept loose; backend is the schema authority) ---

export interface SettingDef {
  name: string;
  type: string;
  label: string;
  description: string;
  default: unknown;
  minimum: unknown;
  maximum: unknown;
  depends_on: string | null;
  advanced: boolean;
  usage: string | null;
  /** Either an array of {value,label} pairs OR camera-driver placeholder
   *  strings like ["bin_values"] which upstream PHP resolves at install time. */
  options: Array<{ label: string; value: unknown } | string> | null;
  /** "reload", "restart", null, etc. — hint that changing this triggers
   *  Allsky to restart on apply. */
  action: string | null;
}

export type SettingsSchema = Record<string, Record<string, SettingDef[]>>;


export interface SystemSnapshot {
  host: {
    boot_time: number;
    uptime_seconds: number;
    cpu_percent: number;
    cpu_temp_c: number | null;
    load_avg: { "1m": number; "5m": number; "15m": number };
    memory: { total: number; available: number; percent: number };
    disk: { path: string; total: number; used: number; free: number; percent: number };
  };
  allsky: {
    version: string;
    status: string;
    raw: unknown;
    camera: { connected: string[]; active: string | null; active_model: string | null };
  };
}

export interface ImageRow {
  path: string;
  date_dir: string;
  filename: string;
  captured_at: number;
  size_bytes: number;
  width: number | null;
  height: number | null;
  exposure_us: number | null;
  iso: number | null;
  has_thumbnail: number;
}

export const api = {
  health: () => request<{ ok: boolean; version: string }>("/health"),
  system: () => request<SystemSnapshot>("/system"),
  messages: () => request<Array<{ type: string; timestamp: string; id: string; message: string }>>(
    "/system/messages",
  ),
  serviceControl: (verb: "start" | "stop" | "restart" | "status") =>
    request<{ verb: string; exit_code: number; stdout: string; stderr: string }>(
      `/system/service/${verb}`, { method: "POST" },
    ),

  settingsSchema: () => request<SettingsSchema>("/settings/schema"),
  settingsAudit: () => request<Array<{
    id: number; ts: number; actor: string | null;
    key: string; old_value: string | null; new_value: string | null;
  }>>("/settings/audit"),
  settingsValues: () => request<Record<string, unknown>>("/settings"),
  patchSettings: (patch: Record<string, unknown>) =>
    request<{ ok: boolean }>("/settings", { method: "PATCH", json: patch }),

  days: () => request<{ dates: string[] }>("/images/days"),
  images: (params: { date: string; sort?: string; order?: string; limit?: number; offset?: number }) =>
    request<{ date: string; total: number; items: ImageRow[] }>(
      `/images?${new URLSearchParams(params as Record<string, string>)}`,
    ),

  masks: () => request<{
    masks: Array<{ name: string; width: number; height: number; size_bytes: number }>;
    frame_dimensions: { width: number; height: number } | null;
  }>("/masks"),
  uploadMask: async (name: string, png: Blob) => {
    const res = await fetch(`${base}/masks/${encodeURIComponent(name)}`, {
      method: "PUT",
      headers: { "Content-Type": "image/png" },
      body: png,
    });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.json();
  },

  keograms: () => request<{ items: Array<{ name: string; size_bytes: number; mtime: number }> }>(
    "/keograms/keograms",
  ),
  startrails: () => request<{ items: Array<{ name: string; size_bytes: number; mtime: number }> }>(
    "/keograms/startrails",
  ),

  alerts: () => request<Array<{
    id: number; level: string; source: string; message: string;
    created_at: number; acknowledged_at: number | null;
  }>>("/alerts"),
  ackAlert: (id: number) => request<{ ok: boolean }>(`/alerts/${id}/ack`, { method: "POST" }),
};

export const fileUrl = {
  imageThumb: (path: string) => `${base}/images/thumb?path=${encodeURIComponent(path)}`,
  imageFull: (path: string) => `${base}/images/file?path=${encodeURIComponent(path)}`,
  keogram: (name: string) => `${base}/keograms/keograms/${encodeURIComponent(name)}`,
  startrail: (name: string) => `${base}/keograms/startrails/${encodeURIComponent(name)}`,
  liveLatest: () => `${base}/live/latest.jpg`,
  mask: (name: string) => `${base}/masks/${encodeURIComponent(name)}`,
};
