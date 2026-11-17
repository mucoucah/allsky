import { apiBase, request, ApiError } from "./client";
import type { SettingsSchema } from "./types";

export const cameraApi = {
  settingsSchema: () => request<SettingsSchema>("/settings/schema"),
  settingsAudit: () => request<Array<{
    id: number; ts: number; actor: string | null;
    key: string; old_value: string | null; new_value: string | null;
  }>>("/settings/audit"),
  settingsValues: () => request<Record<string, unknown>>("/settings"),
  patchSettings: (patch: Record<string, unknown>) =>
    request<{ ok: boolean }>("/settings", { method: "PATCH", json: patch }),
  masks: () => request<{
    masks: Array<{ name: string; width: number; height: number; size_bytes: number }>;
    frame_dimensions: { width: number; height: number } | null;
  }>("/masks"),
  uploadMask: async (name: string, png: Blob) => {
    const res = await fetch(`${apiBase}/masks/${encodeURIComponent(name)}`, {
      method: "PUT",
      headers: { "Content-Type": "image/png" },
      body: png,
    });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.json();
  },
  setupStatus: () => request<{
    configured: boolean; has_camera: boolean; allsky_status: string;
    camera_type: string | null; camera_model: string | null;
    latitude?: string; longitude?: string; service_active?: boolean;
  }>("/setup/status"),
  detectCameras: () => request<{
    cameras: Array<{ index: number; model: string; info: string; modes: string[] }>;
  }>("/setup/detect-cameras"),
  configure: (body: {
    camera_type?: string; camera_model?: string; camera_number?: number;
    latitude?: string; longitude?: string; start_capture?: boolean;
  }) => request<{ ok: boolean; service_started?: boolean }>("/setup/configure", { method: "POST", json: body }),
  enableCamera: () => request<{ results: unknown[]; needs_reboot: boolean; message: string }>(
    "/setup/enable-camera", { method: "POST" },
  ),
  geocode: (q: string) => request<{
    found: boolean; latitude?: string; longitude?: string;
    display_name?: string; city?: string; state?: string; country?: string;
  }>(`/setup/geocode?q=${encodeURIComponent(q)}`),
  cameraOverlays: () => request<{
    overlays: Record<string, { known: boolean; sensor: string; overlay: string; label: string; installed: boolean }>;
  }>("/setup/camera-overlays"),
  installOverlay: (sensor: string) => request<{
    ok: boolean; needs_reboot: boolean; message: string; already_installed?: boolean;
  }>("/setup/install-overlay", { method: "POST", json: { sensor } }),
  reboot: () => request<{ ok: boolean; message: string }>("/setup/reboot", { method: "POST" }),
  overlayConfig: () => request<{
    config_dir: string; exists: boolean;
    fields: Array<{ name: string; label?: string; description?: string }>;
    configs: string[];
  }>("/maintenance/overlay/config"),
  overlayLayout: (name: string) => request<any>(`/maintenance/overlay/layout/${encodeURIComponent(name)}`),
  saveOverlayLayout: (name: string, body: unknown) =>
    request<{ ok: boolean }>(`/maintenance/overlay/layout/${encodeURIComponent(name)}`, { method: "PUT", json: body }),
};
