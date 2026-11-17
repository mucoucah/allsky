import { apiBase, request } from "./client";
import type { AllskyDiskUsage, OffloadConfig, PiHeartbeatStatus, SystemSnapshot, ThermalConfig } from "./types";

export const systemApi = {
  thermal: () => request<ThermalConfig>("/system/thermal"),
  setThermal: (cfg: Partial<ThermalConfig>) =>
    request<{ ok: boolean; config: ThermalConfig }>("/system/thermal", { method: "PUT", json: cfg }),
  offload: () => request<OffloadConfig>("/offload"),
  saveOffload: (cfg: OffloadConfig) =>
    request<OffloadConfig>("/offload", { method: "PUT", json: cfg }),
  offloadPi: () => request<{ ok: boolean; status: PiHeartbeatStatus | null; message?: string }>("/offload/pi"),
  system: () => request<SystemSnapshot>("/system"),
  allskyDisk: () => request<AllskyDiskUsage>("/system/allsky-disk"),
  throttleHistory: () => request<{
    events: Array<{
      ts: number; types: string[];
      cpu_temp_c: number | null; cpu_percent: number | null;
      activity: string;
    }>;
  }>("/system/throttle-history"),
  clearThrottleHistory: () => request<{ ok: boolean }>("/system/throttle-history/clear", { method: "POST" }),
  rebootPi: () => request<{ ok: boolean; message: string }>("/system/reboot", { method: "POST" }),
  shutdownPi: () => request<{ ok: boolean; message: string }>("/system/shutdown", { method: "POST" }),
  messages: () => request<Array<{ type: string; timestamp: string; id: string; message: string }>>(
    "/system/messages",
  ),
  serviceControl: (verb: "start" | "stop" | "restart" | "status") =>
    request<{ verb: string; exit_code: number; stdout: string; stderr: string }>(
      `/system/service/${verb}`, { method: "POST" },
    ),
  logTail: async (lines: number = 200): Promise<string> => {
    const res = await fetch(`${apiBase}/logs/allsky?lines=${lines}`);
    return res.text();
  },
  logTailWebui: async (lines: number = 200): Promise<string> => {
    const res = await fetch(`${apiBase}/logs/webui?lines=${lines}`);
    return res.text();
  },
  checkUpdate: () => request<{
    installed: string; latest: string | null;
    update_available: boolean;
    web_version: string; web_latest: string | null;
    web_update_available: boolean;
    error?: string;
  }>("/maintenance/check-update"),
  listDarks: () => request<{
    darks: Array<{ name: string; size_bytes: number; mtime: number; temperature_c: number | null }>;
    darks_dir: string; total_bytes: number;
  }>("/maintenance/darks"),
  deleteDark: (name: string) =>
    request<{ deleted: string }>(`/maintenance/darks/${encodeURIComponent(name)}`, { method: "DELETE" }),
  captureDark: () =>
    request<{ ok: boolean; message?: string; error?: string }>("/maintenance/darks/capture", { method: "POST" }),
};
