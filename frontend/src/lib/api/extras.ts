import { request } from "./client";
import type { AdsbConfig, AircraftInfo, NotifChannel, RainConfig, SatConfig, SatPass, SatPosition } from "./types";

export const extrasApi = {
  alerts: () => request<Array<{
    id: number; level: string; source: string; message: string;
    created_at: number; acknowledged_at: number | null;
  }>>("/alerts"),
  ackAlert: (id: number) => request<{ ok: boolean }>(`/alerts/${id}/ack`, { method: "POST" }),
  notifChannels: () => request<{ channels: NotifChannel[] }>("/notifications/channels"),
  createChannel: (ch: Partial<NotifChannel>) =>
    request<NotifChannel>("/notifications/channels", { method: "POST", json: ch }),
  updateChannel: (id: string, ch: Partial<NotifChannel>) =>
    request<NotifChannel>(`/notifications/channels/${id}`, { method: "PUT", json: ch }),
  deleteChannel: (id: string) =>
    request<{ deleted: string }>(`/notifications/channels/${id}`, { method: "DELETE" }),
  testChannel: (id: string) =>
    request<{ ok: boolean }>(`/notifications/channels/${id}/test`, { method: "POST" }),
  manualSend: (body: { subject: string; body: string; include_snapshot?: boolean; include_timelapse?: boolean }) =>
    request<{ results: Record<string, boolean> }>("/notifications/send", { method: "POST", json: body }),
  rainConfig: () => request<RainConfig>("/notifications/rain/config"),
  setRainConfig: (cfg: Partial<RainConfig>) =>
    request<{ ok: boolean }>("/notifications/rain/config", { method: "PUT", json: cfg }),
  detectRainNow: () => request<{
    rain_detected: boolean; confidence: number; droplet_count: number;
    contrast_score: number; message: string;
  }>("/notifications/rain/detect-now", { method: "POST" }),
  adsbConfig: () => request<AdsbConfig>("/notifications/adsb/config"),
  setAdsbConfig: (cfg: Partial<AdsbConfig>) =>
    request<{ ok: boolean }>("/notifications/adsb/config", { method: "PUT", json: cfg }),
  adsbNearby: () => request<{
    aircraft: AircraftInfo[]; timestamp: number; count: number;
  }>("/notifications/adsb/nearby"),
  adsbScanNow: () => request<{
    aircraft: AircraftInfo[]; timestamp: number; count: number;
  }>("/notifications/adsb/scan-now", { method: "POST" }),
  satConfig: () => request<SatConfig>("/notifications/satellites/config"),
  setSatConfig: (cfg: Partial<SatConfig>) =>
    request<{ ok: boolean }>("/notifications/satellites/config", { method: "PUT", json: cfg }),
  satPasses: () => request<{
    passes: SatPass[]; overhead: SatPosition[]; timestamp: number;
  }>("/notifications/satellites/passes"),
  satScanNow: () => request<{
    passes: SatPass[]; overhead: SatPosition[]; timestamp: number;
  }>("/notifications/satellites/scan-now", { method: "POST" }),
  testUpload: (cfg: Record<string, unknown>) =>
    request<{ ok: boolean; exit_code?: number; output?: string; error?: string }>(
      "/maintenance/upload/test", { method: "POST", json: cfg }),
};
