/** Shared fetch helper. Section modules build on this. */

export const apiBase = "/api";

export async function request<T>(
  path: string,
  init?: RequestInit & { json?: unknown },
): Promise<T> {
  const opts: RequestInit = { ...init, headers: { ...(init?.headers || {}) } };
  if (init?.json !== undefined) {
    opts.body = JSON.stringify(init.json);
    (opts.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await fetch(`${apiBase}${path}`, opts);
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
    this.name = "ApiError";
  }
}

export const fileUrl = {
  imageThumb: (path: string) => `${apiBase}/images/thumb?path=${encodeURIComponent(path)}`,
  imageFull: (path: string) => `${apiBase}/images/file?path=${encodeURIComponent(path)}`,
  keogram: (name: string) => `${apiBase}/keograms/keograms/${encodeURIComponent(name)}`,
  startrail: (name: string) => `${apiBase}/keograms/startrails/${encodeURIComponent(name)}`,
  liveLatest: (bust?: number) => `${apiBase}/live/latest.jpg${bust ? `?t=${bust}` : ""}`,
  mask: (name: string) => `${apiBase}/masks/${encodeURIComponent(name)}`,
  video: (name: string) => `${apiBase}/keograms/videos/${encodeURIComponent(name)}`,
};
