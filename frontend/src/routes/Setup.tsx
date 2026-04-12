import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, MapPin, Check, RefreshCw } from "lucide-react";
import { api } from "../lib/api";

/** First-time setup wizard.
 *
 *  Shown when the system hasn't been configured yet (no camera model set).
 *  Guides the user through camera detection, location, and initial config. */
export default function Setup() {
  const qc = useQueryClient();
  const { data: status } = useQuery({ queryKey: ["setupStatus"], queryFn: api.setupStatus });
  const { data: cameras, refetch: rescan, isFetching: scanning } = useQuery({
    queryKey: ["cameras"],
    queryFn: api.detectCameras,
  });

  const [selectedCamera, setSelectedCamera] = useState<number>(0);
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [done, setDone] = useState(false);

  const configure = useMutation({
    mutationFn: () => {
      const cam = cameras?.cameras[selectedCamera];
      return api.configure({
        camera_type: "RPi",
        camera_model: cam?.model ?? "",
        camera_number: cam?.index ?? 0,
        latitude: lat,
        longitude: lon,
      });
    },
    onSuccess: () => {
      setDone(true);
      qc.invalidateQueries({ queryKey: ["setupStatus"] });
      qc.invalidateQueries({ queryKey: ["system"] });
    },
  });

  if (status?.configured && status?.has_camera && !done) {
    return (
      <div className="card max-w-xl mx-auto text-center py-8">
        <Check size={48} className="text-ok mx-auto mb-4" />
        <h2 className="text-lg font-semibold mb-2">Already configured</h2>
        <p className="text-ink-muted text-sm">
          Camera: {status.camera_model || status.camera_type || "—"}
        </p>
        <p className="text-ink-dim text-xs mt-2">
          To reconfigure, use the Settings page or run this wizard again.
        </p>
      </div>
    );
  }

  if (done) {
    return (
      <div className="card max-w-xl mx-auto text-center py-8">
        <Check size={48} className="text-ok mx-auto mb-4" />
        <h2 className="text-lg font-semibold mb-2">Configuration saved</h2>
        <p className="text-ink-muted text-sm mb-4">
          Start capturing by running:{" "}
          <code className="bg-bg-base px-2 py-0.5 rounded text-accent">
            sudo systemctl start allsky
          </code>
        </p>
        <p className="text-ink-dim text-xs">
          Or use the System page to start/stop the camera service.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-6">
      <div className="text-center">
        <h1 className="text-2xl font-bold mb-2">Welcome to Allsky</h1>
        <p className="text-ink-muted">
          Let's set up your sky camera. This takes about a minute.
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
          <div className="text-warn text-sm">
            No cameras detected. Make sure your camera is connected and enabled
            in <code>raspi-config</code> → Interface Options → Camera.
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

      {/* Save */}
      <button
        onClick={() => configure.mutate()}
        disabled={configure.isPending || !cameras?.cameras.length}
        className="w-full py-3 rounded-xl bg-accent text-bg-base text-lg font-semibold disabled:opacity-50"
      >
        {configure.isPending ? "Saving..." : "Save configuration"}
      </button>

      {configure.isError && (
        <div className="text-err text-sm text-center">
          Failed: {(configure.error as Error).message}
        </div>
      )}
    </div>
  );
}
