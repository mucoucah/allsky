import { request } from "./client";
import type { FocusConfig, MeteorConfig, MeteorHit } from "./types";

export const tonightApi = {
  meteorConfig: () => request<MeteorConfig>("/notifications/meteor/config"),
  setMeteorConfig: (cfg: Partial<MeteorConfig>) =>
    request<{ ok: boolean }>("/notifications/meteor/config", { method: "PUT", json: cfg }),
  detectMeteorNow: () => request<{
    meteor_count: number; line_count: number; lines: number[][];
  }>("/notifications/meteor/detect-now", { method: "POST" }),
  focusConfig: () => request<FocusConfig>("/notifications/focus/config"),
  setFocusConfig: (cfg: Partial<FocusConfig>) =>
    request<{ ok: boolean }>("/notifications/focus/config", { method: "PUT", json: cfg }),
  calibrateFocus: () =>
    request<{ ok: boolean; baseline_sharpness: number }>("/notifications/focus/calibrate", { method: "POST" }),
  currentFocus: () => request<{
    score: number | null; baseline: number | null; threshold: number | null; status: string;
  }>("/notifications/focus/current"),
  meteorHits: () => request<{ hits: MeteorHit[]; total: number }>("/notifications/meteor/hits"),
};
