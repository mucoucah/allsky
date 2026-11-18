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
    thermal?: {
      enabled: boolean;
      state: "ok" | "warm" | "stopped";
      temp_c: number | null;
      warn_c: number;
      stop_c: number;
      resume_c: number;
      poll_seconds: number;
      skip_processing: boolean;
      extra_delay_ms: number;
      throttled: boolean;
      capture_held: boolean;
      message: string;
    } | null;
  };
  allsky: {
    version: string;
    status: string;
    service_active?: boolean;
    raw: unknown;
    camera: { connected: string[]; active: string | null; active_model: string | null };
  };
  storage?: {
    data_dir: string;
    free_bytes: number;
    free_gb: number;
    total_bytes: number;
    raw_retention_days: number;
    min_free_gb: number;
    disk_guard: { active: boolean; free_gb: number | null; since: string | null };
  } | null;
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

export interface OffloadConfig {
  mode: "normal" | "capture-only";
  jpeg_quality: number;
  outbox_dir: string;
  outbox_max_bytes: number;
  drop_day_frames: boolean;
  night_priority: boolean;
  remote: {
    host: string;
    port: number;
    user: string;
    path: string;
    ssh_key: string;
    bandwidth_limit_kbps: number;
    settings_path: string;
    status_name: string;
  };
  processor: {
    incoming_dir: string;
    data_dir: string;
    to_pi_dir: string;
    retention_days: number;
    raw_retention_days: number;
    min_free_gb: number;
    max_disk_bytes: number;
    encoder: string;
    meteor_scale: number;
    use_cuda: string;
    min_streak_length: number;
    poll_seconds: number;
    quiet_with_day_seconds: number;
    quiet_alone_seconds: number;
  };
  persisted?: boolean;
  path?: string | null;
}

export interface PiHeartbeatStatus {
  timestamp: string;
  hostname?: string;
  mode?: string;
  temp_c: number | null;
  throttled?: {
    raw: string;
    throttled_now?: boolean;
    soft_temp_limit_now?: boolean;
    any_now?: boolean;
  };
  disk?: { free: number; total: number; percent: number };
  outbox_bytes?: number;
  outbox_files?: number;
  last_frame_time: string | null;
  last_frame_name?: string | null;
  camera_error: string | null;
  thermal_state?: string;
}

export interface NotifChannel {
  id: string;
  type: string;
  name: string;
  enabled: boolean;
  config: Record<string, string>;
  send_snapshot: boolean;
  send_timelapse: boolean;
}

export interface MeteorHit {
  date: string;
  id: string;
  time: string | null;
  meteor_count: number | null;
  lines: Array<{ x1: number; y1: number; x2: number; y2: number }>;
  frame: string | null;
  crop: string | null;
  crop_url: string | null;
  frame_url: string | null;
}

export interface MeteorConfig {
  enabled: boolean;
  poll_interval_minutes: number;
  alert_cooldown_minutes?: number;
  min_streak_length: number;
  include_snapshot: boolean;
  include_timelapse: boolean;
  [k: string]: unknown;
}

export interface ThermalConfig {
  enabled: boolean;
  warn_c: number;
  stop_c: number;
  resume_c: number;
  poll_seconds: number;
  warm_extra_delay_ms: number;
  state?: string;
  temp_c?: number | null;
  message?: string;
  skip_processing?: boolean;
  extra_delay_ms?: number;
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
  geo_altitude_m: number | null;
  position_source: string;
  category: string;
  spi: boolean;
  last_contact_age: number;
  registration: string;
  aircraft_type: string;
  operator: string;
}

export interface SatConfig {
  enabled: boolean;
  poll_interval_minutes: number;
  tle_groups: string[];
  hours_ahead: number;
  min_elevation_deg: number;
  alert_triggers: string[];
  alert_min_elevation_deg: number;
  alert_minutes_before: number;
  alert_cooldown_minutes: number;
  include_snapshot: boolean;
}

export interface SatPass {
  name: string;
  norad_id: string;
  rise_time: string;
  rise_az_deg: number;
  culmination_time: string;
  max_elev_deg: number;
  set_time: string;
  set_az_deg: number;
  duration_sec: number;
  is_visible: boolean;
  group: string;
}

export interface SatPosition {
  name: string;
  norad_id: string;
  lat: number;
  lon: number;
  altitude_km: number;
  velocity_kms: number;
  elevation_deg: number;
  azimuth_deg: number;
  range_km: number;
  is_sunlit: boolean;
  group: string;
}

export interface DailylapseOpts {
  mode: "fixed" | "sunrise" | "sunset" | "solar_noon";
  clock_time?: string;
  start_date?: string;
  end_date?: string;
  max_offset_min?: number;
  fps?: number;
  label?: string;
}

export interface DailylapseFrame {
  date: string;
  target_time: string;
  actual_time: string;
  offset_sec: number;
  filename: string;
}

export interface DailylapseVideo {
  name: string;
  size_mb: number;
  created: number;
  url: string;
}
