import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Camera, MapPin, Check, RefreshCw, Play, Wifi } from "lucide-react";
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
          <div className="rounded-xl bg-warn/10 border border-warn/30 p-4 flex flex-col gap-3">
            <div className="text-warn text-sm font-medium">
              No cameras detected
            </div>
            <p className="text-xs text-ink-muted">
              Make sure your camera ribbon cable is connected. If this is a fresh
              Pi setup, the camera interface may need to be enabled.
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => enableCamera.mutate()}
                disabled={enableCamera.isPending}
                className="px-3 py-1.5 rounded-lg bg-warn text-bg-base text-sm font-medium inline-flex items-center gap-1.5"
              >
                <Wifi size={14} />
                {enableCamera.isPending ? "Enabling..." : "Enable camera interface"}
              </button>
              {enableCamera.isSuccess && enableCamera.data?.needs_reboot && (
                <button
                  onClick={() => reboot.mutate()}
                  disabled={reboot.isPending}
                  className="px-3 py-1.5 rounded-lg bg-err text-white text-sm font-medium"
                >
                  {reboot.isPending ? "Rebooting..." : "Reboot now"}
                </button>
              )}
            </div>
            {enableCamera.isSuccess && !enableCamera.data?.needs_reboot && (
              <p className="text-xs text-ok">
                Camera interface already enabled. Try scanning again.
              </p>
            )}
            {enableCamera.isSuccess && enableCamera.data?.needs_reboot && (
              <p className="text-xs text-warn">
                Camera interface enabled. A reboot is required — click the button above,
                then reload this page after about 60 seconds.
              </p>
            )}
            {reboot.isSuccess && (
              <p className="text-xs text-ink-muted">
                Rebooting... this page will stop responding. Reload in about 60 seconds.
              </p>
            )}
          </div>
        ) : null}
      </section>

      {/* Step 2: Location */}
      <section className="card">
        <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
          <MapPin size={20} /> 2. Location (optional)
        </h2>
        <p className="text-xs text-ink-dim mb-3">
          Used for day/night calculation and constellation overlays.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-ink-muted">Latitude</span>
            <input
              type="text"
              placeholder="e.g. 51.5074"
              value={lat}
              onChange={(e) => setLat(e.target.value)}
              className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm font-mono"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-ink-muted">Longitude</span>
            <input
              type="text"
              placeholder="e.g. -0.1278"
              value={lon}
              onChange={(e) => setLon(e.target.value)}
              className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm font-mono"
            />
          </label>
        </div>
      </section>

      {/* Save + Start */}
      <button
        onClick={() => configure.mutate()}
        disabled={configure.isPending || !cameras?.cameras.length}
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
