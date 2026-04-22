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
    cpu_info: { cores_physical: number | null; cores_logical: number | null; architecture: string };
    load_avg: { "1m": number; "5m": number; "15m": number };
    memory: { total: number; available: number; used: number; percent: number };
    swap: { total: number; used: number; free: number; percent: number };
    disk: { path: string; total: number; used: number; free: number; percent: number };
    disk_root: { path: string; total: number; used: number; free: number; percent: number };
    pi_model: string | null;
    hostname: string;
    os: string;
    python_version: string;
    current_activity?: string;
    time?: {
      system_time: string;
      timezone: string;
      timezone_name?: string;
      utc_time: string;
      unix_timestamp: number;
      latitude?: number | null;
      longitude?: number | null;
      day_night_angle?: number | string;
      sun_elevation_deg?: number;
      sun_azimuth_deg?: number;
      is_day?: boolean;
      day_night_status?: "DAY" | "NIGHT";
      next_sunrise_local?: string;
      next_sunset_local?: string;
      sun_elevation_note?: string;
      sun_calc_error?: string;
      moon?: {
        elevation_deg: number;
        azimuth_deg: number;
        illumination_pct: number;
        phase_name: string;
        phase_fraction: number;
        age_days: number;
        is_visible: boolean;
      };
    };
    network: Array<{
      name: string; is_up: boolean; speed_mbps?: number;
      bytes_sent?: number; bytes_recv?: number;
      addresses: Array<{ family: string; address: string; netmask: string | null }>;
    }>;
    throttle: {
      raw: string;
      under_voltage_now: boolean; freq_capped_now: boolean;
      throttled_now: boolean; soft_temp_limit_now: boolean;
      under_voltage_occurred: boolean; freq_capped_occurred: boolean;
      throttled_occurred: boolean; soft_temp_limit_occurred: boolean;
    } | null;
  };
  allsky: {
    version: string;
    status: string;
    service_active?: boolean;
    raw: unknown;
    camera: { connected: string[]; active: string | null; active_model: string | null };
  };
}

export interface AllskyDiskUsage {
  images: number; darks: number; keograms: number;
  startrails: number; videos: number; config: number; tmp: number;
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

  // Setup wizard
  setupStatus: () => request<{
    configured: boolean; has_camera: boolean; allsky_status: string;
    camera_type: string | null; camera_model: string | null;
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
    const res = await fetch(`${base}/logs/allsky?lines=${lines}`);
    return res.text();
  },
  logTailWebui: async (lines: number = 200): Promise<string> => {
    const res = await fetch(`${base}/logs/webui?lines=${lines}`);
    return res.text();
  },

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
  videos: (params?: { date?: string; sort?: string; order?: string }) =>
    request<{
      items: Array<{ name: string; size_bytes: number; mtime: number; date: string | null }>;
      dates: string[];
      total: number;
    }>(`/keograms/videos${params ? `?${new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v != null)) as Record<string, string>
    )}` : ""}`),

  alerts: () => request<Array<{
    id: number; level: string; source: string; message: string;
    created_at: number; acknowledged_at: number | null;
  }>>("/alerts"),
  ackAlert: (id: number) => request<{ ok: boolean }>(`/alerts/${id}/ack`, { method: "POST" }),

  // Notification channels
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

  // Meteor detection
  meteorConfig: () => request<MeteorConfig>("/notifications/meteor/config"),
  setMeteorConfig: (cfg: Partial<MeteorConfig>) =>
    request<{ ok: boolean }>("/notifications/meteor/config", { method: "PUT", json: cfg }),
  detectMeteorNow: () => request<{
    meteor_count: number; line_count: number; lines: number[][];
  }>("/notifications/meteor/detect-now", { method: "POST" }),

  // Focus monitoring
  focusConfig: () => request<FocusConfig>("/notifications/focus/config"),
  setFocusConfig: (cfg: Partial<FocusConfig>) =>
    request<{ ok: boolean }>("/notifications/focus/config", { method: "PUT", json: cfg }),
  calibrateFocus: () =>
    request<{ ok: boolean; baseline_sharpness: number }>("/notifications/focus/calibrate", { method: "POST" }),
  // Rain detection
  rainConfig: () => request<RainConfig>("/notifications/rain/config"),
  setRainConfig: (cfg: Partial<RainConfig>) =>
    request<{ ok: boolean }>("/notifications/rain/config", { method: "PUT", json: cfg }),
  detectRainNow: () => request<{
    rain_detected: boolean; confidence: number; droplet_count: number;
    contrast_score: number; message: string;
  }>("/notifications/rain/detect-now", { method: "POST" }),

  // ADS-B aircraft tracking
  adsbConfig: () => request<AdsbConfig>("/notifications/adsb/config"),
  setAdsbConfig: (cfg: Partial<AdsbConfig>) =>
    request<{ ok: boolean }>("/notifications/adsb/config", { method: "PUT", json: cfg }),
  adsbNearby: () => request<{
    aircraft: AircraftInfo[]; timestamp: number; count: number;
  }>("/notifications/adsb/nearby"),
  adsbScanNow: () => request<{
    aircraft: AircraftInfo[]; timestamp: number; count: number;
  }>("/notifications/adsb/scan-now", { method: "POST" }),

  // Maintenance: updates, darks, upload tests, generate for day
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
  testUpload: (cfg: Record<string, unknown>) =>
    request<{ ok: boolean; exit_code?: number; output?: string; error?: string }>(
      "/maintenance/upload/test", { method: "POST", json: cfg }),
  availableDates: () => request<{
    dates: Array<{ date: string; image_count: number }>;
  }>("/maintenance/generate/dates"),
  generateForDate: (date: string, kinds: string[]) =>
    request<{ ok: boolean; exit_code?: number; output?: string; error?: string; date: string; kinds: string[] }>(
      `/maintenance/generate/${date}`, { method: "POST", json: { kinds } }),
  overlayConfig: () => request<{
    config_dir: string; exists: boolean;
    fields: Array<{ name: string; label?: string; description?: string }>;
    configs: string[];
  }>("/maintenance/overlay/config"),
  overlayLayout: (name: string) => request<any>(`/maintenance/overlay/layout/${encodeURIComponent(name)}`),
  saveOverlayLayout: (name: string, body: unknown) =>
    request<{ ok: boolean }>(`/maintenance/overlay/layout/${encodeURIComponent(name)}`, { method: "PUT", json: body }),

  currentFocus: () => request<{
    score: number | null; baseline: number | null; threshold: number | null; status: string;
  }>("/notifications/focus/current"),
};

export interface NotifChannel {
  id: string;
  type: string;
  name: string;
  enabled: boolean;
  config: Record<string, string>;
  send_snapshot: boolean;
  send_timelapse: boolean;
}

export interface MeteorConfig {
  enabled: boolean;
  poll_interval_minutes: number;
  min_streak_length: number;
  include_snapshot: boolean;
  include_timelapse: boolean;
  [k: string]: unknown;
}

export interface FocusConfig {
  enabled: boolean;
  poll_interval_minutes: number;
  baseline_sharpness: number | null;
  threshold_pct: number;
  consecutive_failures_to_alert: number;
  include_snapshot: boolean;
}

export interface RainConfig {
  enabled: boolean;
  poll_interval_minutes: number;
  confidence_threshold: number;
  include_snapshot: boolean;
}

export interface AdsbConfig {
  enabled: boolean;
  poll_interval_seconds: number;
  radius_km: number;
  min_altitude_m: number;
  show_on_overlay: boolean;
  overlay_max_aircraft: number;
  alert_triggers: string[];
  alert_low_altitude_ft: number;
  alert_slow_speed_kts: number;
  alert_cooldown_minutes: number;
  opensky_username: string;
  opensky_password: string;
  include_snapshot: boolean;
}

export interface AircraftInfo {
  icao24: string;
  callsign: string;
  origin_country: string;
  lat: number;
  lon: number;
  altitude_m: number | null;
  velocity_mps: number | null;
  heading_deg: number | null;
  vertical_rate: number | null;
  on_ground: boolean;
  squawk: string | null;
  distance_km: number;
  bearing_deg: number;
  elevation_deg: number;
}

export const fileUrl = {
  imageThumb: (path: string) => `${base}/images/thumb?path=${encodeURIComponent(path)}`,
  imageFull: (path: string) => `${base}/images/file?path=${encodeURIComponent(path)}`,
  keogram: (name: string) => `${base}/keograms/keograms/${encodeURIComponent(name)}`,
  startrail: (name: string) => `${base}/keograms/startrails/${encodeURIComponent(name)}`,
  liveLatest: (bust?: number) => `${base}/live/latest.jpg${bust ? `?t=${bust}` : ""}`,
  mask: (name: string) => `${base}/masks/${encodeURIComponent(name)}`,
  video: (name: string) => `${base}/keograms/videos/${encodeURIComponent(name)}`,
};
