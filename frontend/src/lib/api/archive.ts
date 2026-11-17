import { request } from "./client";
import type { DailylapseFrame, DailylapseOpts, DailylapseVideo, ImageRow } from "./types";

export const archiveApi = {
  days: () => request<{ dates: string[] }>("/images/days"),
  images: (params: { date: string; sort?: string; order?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value != null) query.set(key, String(value));
    }
    return request<{ date: string; total: number; items: ImageRow[] }>(`/images?${query}`);
  },
  keograms: () => request<{ items: Array<{ name: string; size_bytes: number; mtime: number }> }>(
    "/keograms/keograms",
  ),
  startrails: () => request<{ items: Array<{ name: string; size_bytes: number; mtime: number }> }>(
    "/keograms/startrails",
  ),
  videos: (params?: { date?: string; sort?: string; order?: string }) =>
    request<{
      items: Array<{ name: string; size_bytes: number; mtime: number; date: string | null }>;
      dates: string[];
      total: number;
    }>(`/keograms/videos${params ? `?${new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v != null)) as Record<string, string>
    )}` : ""}`),
  dailylapsePreview: (opts: DailylapseOpts) =>
    request<{ frame_count: number; frames: DailylapseFrame[] }>("/maintenance/dailylapse/preview", { method: "POST", json: opts }),
  dailylapseGenerate: (opts: DailylapseOpts) =>
    request<{ ok: boolean; frames_used: number; date_range: string; video_url: string }>(
      "/maintenance/dailylapse/generate", { method: "POST", json: opts }),
  dailylapseList: () =>
    request<{ videos: DailylapseVideo[] }>("/maintenance/dailylapse/list"),
  dailylapseDelete: (label: string) =>
    request<{ ok: boolean }>(`/maintenance/dailylapse/video/${label}`, { method: "DELETE" }),
  availableDates: () => request<{
    dates: Array<{ date: string; image_count: number }>;
  }>("/maintenance/generate/dates"),
  generateForDate: (date: string, kinds: string[]) =>
    request<{ ok: boolean; exit_code?: number; output?: string; error?: string; date: string; kinds: string[] }>(
      `/maintenance/generate/${date}`, { method: "POST", json: { kinds } }),
};
