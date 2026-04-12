import { useState, useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Camera, MapPin, Check, RefreshCw, Play, Wifi, Settings, Search } from "lucide-react";
import { api } from "../lib/api";

/** Full setup wizard — user never needs a terminal after install.sh.
 *
 *  Flow:
 *    1. Detect camera (or enable camera interface + reboot if none found)
 *    2. Pick latitude/longitude
 *    3. Save → auto-starts allsky service
 *    4. Redirect to dashboard */
export default function Setup() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ["setupStatus"],
    queryFn: api.setupStatus,
  });
  const {
    data: cameras,
    refetch: rescan,
    isFetching: scanning,
  } = useQuery({
    queryKey: ["cameras"],
    queryFn: api.detectCameras,
  });

  const [selectedCamera, setSelectedCamera] = useState<number>(0);
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [step, setStep] = useState<"detect" | "configure" | "done">("detect");

  const enableCamera = useMutation({ mutationFn: api.enableCamera });
  const reboot = useMutation({ mutationFn: api.reboot });

  const configure = useMutation({
    mutationFn: () => {
      const cam = cameras?.cameras[selectedCamera];
      return api.configure({
        camera_type: "RPi",
        camera_model: cam?.model ?? "",
        camera_number: cam?.index ?? 0,
        latitude: lat,
        longitude: lon,
        start_capture: true,
      });
    },
    onSuccess: () => {
      setStep("done");
      qc.invalidateQueries({ queryKey: ["setupStatus"] });
      qc.invalidateQueries({ queryKey: ["system"] });
    },
  });

  const startService = useMutation({
    mutationFn: () => api.serviceControl("start"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["setupStatus"] });
      qc.invalidateQueries({ queryKey: ["system"] });
    },
  });

  // Already configured — show summary with controls.
  if (status?.configured && status?.has_camera && step !== "done") {
    return (
      <div className="max-w-xl mx-auto flex flex-col gap-4">
        <div className="card text-center py-6">
          <Check size={48} className="text-ok mx-auto mb-4" />
          <h2 className="text-lg font-semibold mb-2">Camera configured</h2>
          <p className="text-ink-muted text-sm">
            {status.camera_model || status.camera_type || "Unknown camera"}
          </p>
          <div className="flex items-center justify-center gap-2 mt-3">
            <span className={`pill ${status.service_active ? "pill-ok" : "pill-err"}`}>
              {status.service_active ? "running" : "stopped"}
            </span>
          </div>
        </div>

        <div className="card flex flex-wrap gap-2 justify-center">
          {!status.service_active && (
            <button
              onClick={() => startService.mutate()}
              disabled={startService.isPending}
              className="px-4 py-2 rounded-lg bg-ok text-bg-base font-medium inline-flex items-center gap-2"
            >
              <Play size={16} /> Start camera
            </button>
          )}
          {status.service_active && (
            <button
              onClick={() => api.serviceControl("stop").then(() => refetchStatus())}
              className="px-4 py-2 rounded-lg border border-bg-raised text-sm"
            >
              Stop camera
            </button>
          )}
          <button
            onClick={() => { setStep("detect"); }}
            className="px-4 py-2 rounded-lg border border-bg-raised text-sm"
          >
            Reconfigure
          </button>
          <button
            onClick={() => navigate("/")}
            className="px-4 py-2 rounded-lg bg-accent text-bg-base font-medium"
          >
            Go to Dashboard
          </button>
        </div>
      </div>
    );
  }

  // Done step — camera configured and started.
  if (step === "done") {
    return (
      <div className="max-w-xl mx-auto flex flex-col gap-4">
        <div className="card text-center py-8">
          <Check size={48} className="text-ok mx-auto mb-4" />
          <h2 className="text-lg font-semibold mb-2">All set!</h2>
          <p className="text-ink-muted text-sm mb-4">
            Camera configured and capture service started.
          </p>
          <button
            onClick={() => navigate("/")}
            className="px-6 py-2.5 rounded-xl bg-accent text-bg-base text-lg font-semibold"
          >
            Open Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-6">
      <div className="text-center">
        <h1 className="text-2xl font-bold mb-2">Welcome to Allsky</h1>
        <p className="text-ink-muted">
          Let's set up your sky camera. Everything is done right here.
        </p>
      </div>

      {/* Step 1: Camera detection */}
      <section className="card">
        <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
          <Camera size={20} /> 1. Detect camera
        </h2>
        <div className="flex items-center gap-3 mb-3">
          <button
            onClick={() => rescan()}
            disabled={scanning}
            className="px-3 py-1.5 rounded-lg border border-bg-raised text-sm inline-flex items-center gap-1.5"
          >
            <RefreshCw size={14} className={scanning ? "animate-spin" : ""} />
            {scanning ? "Scanning..." : "Scan for cameras"}
          </button>
        </div>

        {cameras && cameras.cameras.length > 0 ? (
          <ul className="divide-y divide-bg-raised">
            {cameras.cameras.map((cam, i) => (
              <li key={i} className="py-2">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="radio"
                    name="camera"
                    checked={selectedCamera === i}
                    onChange={() => setSelectedCamera(i)}
                    className="accent-accent"
                  />
                  <div>
                    <div className="font-mono text-sm">{cam.model}</div>
                    <div className="text-xs text-ink-dim">{cam.info}</div>
                    {cam.modes.length > 0 && (
                      <div className="text-xs text-ink-muted">
                        Modes: {cam.modes.join(", ")}
                      </div>
                    )}
                  </div>
                </label>
              </li>
            ))}
          </ul>
        ) : cameras ? (
          <NoCamerasSection
            enableCamera={enableCamera}
            reboot={reboot}
          />
        ) : null}
      </section>

      {/* Step 2: Location (required) */}
      <LocationSection lat={lat} lon={lon} setLat={setLat} setLon={setLon} />

      {/* Save + Start */}
      <button
        onClick={() => configure.mutate()}
        disabled={configure.isPending || !cameras?.cameras.length || !lat || !lon}
        className="w-full py-3 rounded-xl bg-accent text-bg-base text-lg font-semibold disabled:opacity-50 inline-flex items-center justify-center gap-2"
      >
        <Play size={20} />
        {configure.isPending ? "Configuring & starting..." : "Save & start camera"}
      </button>

      {configure.isError && (
        <div className="text-err text-sm text-center">
          Failed: {(configure.error as Error).message}
        </div>
      )}
    </div>
  );
}

/* ── Location section with zip code lookup ──────────────────── */

function LocationSection({
  lat, lon, setLat, setLon,
}: {
  lat: string; lon: string;
  setLat: (v: string) => void; setLon: (v: string) => void;
}) {
  const [zipQuery, setZipQuery] = useState("");
  const [locationName, setLocationName] = useState("");
  const geocode = useMutation({
    mutationFn: (q: string) => api.geocode(q),
    onSuccess: (data) => {
      if (data.found && data.latitude && data.longitude) {
        setLat(data.latitude);
        setLon(data.longitude);
        const parts = [data.city, data.state, data.country].filter(Boolean);
        setLocationName(parts.join(", ") || data.display_name || "");
      }
    },
  });

  const handleLookup = useCallback(() => {
    if (zipQuery.trim()) geocode.mutate(zipQuery.trim());
  }, [zipQuery, geocode]);

  return (
    <section className="card">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-1">
        <MapPin size={20} /> 2. Location
        <span className="text-xs text-red-400 font-normal">(required)</span>
      </h2>
      <p className="text-xs text-ink-dim mb-3">
        Required for day/night calculation. The camera uses different settings for day vs night.
      </p>

      {/* Zip code / city lookup */}
      <div className="flex gap-2 mb-3">
        <input
          type="text"
          placeholder="Enter zip code or city name..."
          value={zipQuery}
          onChange={(e) => setZipQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleLookup()}
          className="bg-bg-base border border-bg-raised rounded-lg px-3 py-1.5 text-sm flex-1"
        />
        <button
          onClick={handleLookup}
          disabled={!zipQuery.trim() || geocode.isPending}
          className="px-4 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium disabled:opacity-50 inline-flex items-center gap-1.5"
        >
          <Search size={14} />
          {geocode.isPending ? "Looking up..." : "Look up"}
        </button>
      </div>

      {locationName && (
        <div className="text-sm text-ok mb-3 flex items-center gap-1.5">
          <Check size={14} /> {locationName}
        </div>
      )}
      {geocode.isError && (
        <div className="text-xs text-err mb-3">Lookup failed. Enter coordinates manually below.</div>
      )}
      {geocode.isSuccess && !geocode.data?.found && (
        <div className="text-xs text-warn mb-3">Location not found. Try a different search or enter coordinates manually.</div>
      )}

      {/* Manual lat/lon */}
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-ink-muted">Latitude <span className="text-red-400">*</span></span>
          <input
            type="text"
            placeholder="e.g. 27.8006"
            value={lat}
            onChange={(e) => setLat(e.target.value)}
            className={`bg-bg-base border rounded-lg px-2 py-1 text-sm font-mono ${
              lat ? "border-bg-raised" : "border-red-500/50"
            }`}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-ink-muted">Longitude <span className="text-red-400">*</span></span>
          <input
            type="text"
            placeholder="e.g. -97.3964"
            value={lon}
            onChange={(e) => setLon(e.target.value)}
            className={`bg-bg-base border rounded-lg px-2 py-1 text-sm font-mono ${
              lon ? "border-bg-raised" : "border-red-500/50"
            }`}
          />
        </label>
      </div>
      {(!lat || !lon) && (
        <p className="text-xs text-red-400 mt-2">
          Latitude and longitude are required. Enter a zip code above or type coordinates manually.
        </p>
      )}
    </section>
  );
}

/* ── No cameras section with overlay installer ──────────────── */

function NoCamerasSection({
  enableCamera,
  reboot,
}: {
  enableCamera: ReturnType<typeof useMutation<any, any, void>>;
  reboot: ReturnType<typeof useMutation<any, any, void>>;
}) {
  const [selectedSensor, setSelectedSensor] = useState("");
  const installOverlay = useMutation({ mutationFn: (sensor: string) => api.installOverlay(sensor) });
  const { data: overlays } = useQuery({
    queryKey: ["camera-overlays"],
    queryFn: api.cameraOverlays,
  });

  const overlayList = overlays ? Object.values(overlays.overlays) : [];
  const needsReboot = enableCamera.data?.needs_reboot || installOverlay.data?.needs_reboot;

  return (
    <div className="rounded-xl bg-warn/10 border border-warn/30 p-4 flex flex-col gap-4">
      <div className="text-warn text-sm font-medium">No cameras detected</div>
      <p className="text-xs text-ink-muted">
        Make sure your camera ribbon cable is connected. CSI cameras (like IMX290/IMX462)
        need a device tree overlay in <code className="text-ink">/boot/config.txt</code> to be recognized.
      </p>

      {/* Camera overlay installer */}
      <div className="border border-bg-raised rounded-lg p-3 bg-bg-panel/50">
        <div className="flex items-center gap-2 mb-2">
          <Settings size={14} className="text-accent" />
          <span className="text-sm font-medium">Install camera overlay</span>
        </div>
        <p className="text-xs text-ink-dim mb-2">
          Select your camera sensor to add the correct <code>dtoverlay</code> to boot config:
        </p>
        <div className="flex flex-wrap gap-2 items-center">
          <select
            value={selectedSensor}
            onChange={(e) => setSelectedSensor(e.target.value)}
            className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1.5 text-sm flex-1 min-w-[200px]"
          >
            <option value="">Select your camera sensor...</option>
            {overlayList.map((o) => (
              <option key={o.sensor} value={o.sensor}>
                {o.label} {o.installed ? "(already installed)" : ""}
              </option>
            ))}
          </select>
          <button
            onClick={() => selectedSensor && installOverlay.mutate(selectedSensor)}
            disabled={!selectedSensor || installOverlay.isPending}
            className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium disabled:opacity-50"
          >
            {installOverlay.isPending ? "Installing..." : "Install overlay"}
          </button>
        </div>
        {installOverlay.isSuccess && installOverlay.data?.already_installed && (
          <p className="text-xs text-ok mt-2">Overlay already installed. Try scanning again.</p>
        )}
        {installOverlay.isSuccess && installOverlay.data?.needs_reboot && (
          <p className="text-xs text-warn mt-2">
            Overlay added. A reboot is required for the camera to be detected.
          </p>
        )}
      </div>

      {/* Enable camera interface */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => enableCamera.mutate()}
          disabled={enableCamera.isPending}
          className="px-3 py-1.5 rounded-lg bg-warn text-bg-base text-sm font-medium inline-flex items-center gap-1.5"
        >
          <Wifi size={14} />
          {enableCamera.isPending ? "Enabling..." : "Enable camera interface"}
        </button>
      </div>
      {enableCamera.isSuccess && !enableCamera.data?.needs_reboot && (
        <p className="text-xs text-ok">Camera interface already enabled.</p>
      )}

      {/* Reboot button — shown when any action requires reboot */}
      {needsReboot && (
        <div className="border-t border-bg-raised pt-3 flex flex-wrap items-center gap-3">
          <button
            onClick={() => reboot.mutate()}
            disabled={reboot.isPending}
            className="px-4 py-2 rounded-lg bg-err text-white text-sm font-medium"
          >
            {reboot.isPending ? "Rebooting..." : "Reboot now"}
          </button>
          <span className="text-xs text-warn">
            Reboot required for changes to take effect. Reload page after ~60 seconds.
          </span>
        </div>
      )}
      {reboot.isSuccess && (
        <p className="text-xs text-ink-muted">
          Rebooting... this page will stop responding. Reload in about 60 seconds.
        </p>
      )}
    </div>
  );
}
