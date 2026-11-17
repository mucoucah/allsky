# allsky-web v1.14.0

A full fork of the [Allsky](https://github.com/AllskyTeam/allsky) sky camera project with a modern, mobile-first web interface. No PHP, no lighttpd — just FastAPI + React.

**One install, everything works.** Camera capture backend + modern web UI.

## Quick start

```bash
git clone https://github.com/mucoucah/allsky.git
cd allsky
sudo ./install.sh
```

Open `http://<your-pi-ip>:8000` — the setup wizard walks you through camera detection and configuration. The installer asks for a web UI password (or generates one and prints it). No terminal needed after install.

## Hardware

This tree is set up for a night meteor camera on a Raspberry Pi that previously overheated:

- Raspberry Pi 4B, 4 GB
- Arducam industrial camera, Sony STARVIS IMX462 color, 2 MP (1920×1080), fisheye lens
- Driver: the Bullseye or Bookworm libcamera / rpicam-still driver already in Raspberry Pi OS (the IMX462 uses the imx290 overlay)
- Cooling: a heatsink plus a 5 V fan, or a fan case. Use a vented, shaded enclosure and keep the Pi outside the sealed dome
- Power: the official 5 V 3 A supply

Night defaults (milliseconds for exposure and delay; gain is the libcamera linear factor):

| Setting | Value | Why |
| --- | --- | --- |
| Manual night exposure | 8 s | Long enough for meteors, short enough to keep the sensor and the Pi moving |
| Max auto exposure | 10 s | Auto mode cannot run away to a minute-plus exposure |
| Night gain | 16 | About 24 dB. The IMX462 analogue ceiling is **29.4 dB ≈ 29.51×** (`10^(0.015 × gain_code)`, codes 0–98 at 0.3 dB). Higher `--analoggain` values are accepted and the extra is ISP digital gain, which mostly amplifies noise |
| Max auto gain | 29 | Stays inside that analogue range |
| Night delay | 0.5 s | The next frame starts quickly |

`rpicam-still` / `libcamera-still` is started with `--immediate` when Allsky is setting the shutter itself, so the process does not sit in a preview waiting for auto-exposure to settle. A single long-lived camera process would avoid the per-frame startup cost; that is a follow-up, not this change.

## Meteor detection

Enable it under Sky Monitor. It runs only at night (latitude and longitude must be set). Each new frame, not a 15-minute timer, is checked on a worker thread:

1. Grayscale copy, downscaled 2×, with the mask applied (painted areas are ignored).
2. Subtract the previous frame, or a short running median, so stars and static edges drop out.
3. Drop a streak that is still bright on the previous frame or continues a line from that frame (planes and satellites that last more than one exposure).
4. Save a hit as the full frame, a crop, and a small JSON file (line coordinates and time) under `html/allsky/meteors/<date>/`.
5. Send an alert at most once per cooldown (default 10 minutes), not once per day.

While the CPU is warm the focus and rain watchers, overlays, and mini-timelapse pause. Meteor detection itself keeps running until capture is stopped for heat.

## Features

### Camera & imaging
- **Live view** via WebSocket push (no polling)
- **Setup wizard** — auto-detects RPi/ZWO cameras, configures, starts capture
- **Image gallery** with date filtering, EXIF metadata, lightbox
- **Keograms & startrails** viewer with full-screen overlay
- **Dark frame management** — capture, list, download, delete dark frames by temperature
- **Regenerate** keograms, startrails, and timelapse videos for any past date

### Dashboard & system
- **Dashboard** with CPU temp, disk, memory, camera status, focus quality, start/stop buttons
- **Throttle history** — tracks and displays CPU thermal throttling events
- **System control**: start/stop/restart camera, reboot/shutdown, log viewer — all from the browser
- **Version checker** — compares installed vs. latest release for both camera backend and web UI

### Settings & overlays
- **Settings editor** with validation, dependency awareness, audit trail
- **Visual overlay editor** — drag fields, set font size/color/stroke, per-layout configs
- **Visual mask editor** (Konva) with draw/erase, undo/redo

### Detection & monitoring
- **Meteor/streak detection** with configurable sensitivity
- **Focus monitoring** with calibration and cloud-proof hysteresis
- **Rain/moisture detection** — analyzes bright blobs, contrast, and local variance on the dome with confidence scoring

### Aircraft tracking (ADS-B)
ADS-B and the satellite watcher both start **disabled**. Leave them off on a Pi 4 unless the CPU stays cool; each one is extra network and CPU work during the night.
- **OpenSky Network integration** — fetches nearby aircraft positions in real-time
- Computes distance, bearing, and elevation angle relative to camera location
- **Emergency squawk detection** (7500 hijack, 7600 radio failure, 7700 emergency)
- **Aircraft metadata enrichment** — registration (tail number), aircraft type, operator via background API lookups (cached 24h)
- Extra state vector data: position source (ADS-B/MLAT badge), aircraft category (Light/Medium/Heavy/Rotorcraft/UAV), vertical rate, SPI flag
- **Configurable alert triggers**: emergency squawk, all flights, low altitude, slow movers, no callsign — each independently toggleable

### Satellite pass prediction
- **CelesTrak TLE integration** — downloads orbital elements for ISS, Starlink, Hubble, and other bright satellites (free, no API key)
- **Local pass computation** using `ephem` — rise/set times, max elevation, duration, sunlit visibility check
- **Configurable satellite groups**: space stations, bright visual satellites, Starlink constellation
- **Alert triggers**: ISS passes, any space station, bright passes (>45° elevation), Starlink, all visible — each independently toggleable with configurable lead time and cooldown
- **Dashboard card** showing next upcoming pass
- Currently-overhead satellite display with real-time positions

### Alerts & notifications
- **Multi-channel dispatch**: Telegram, Discord, Email, ntfy.sh, webhook
- Per-channel attachment options (snapshot, timelapse)
- **Persistent alert log** with acknowledgment tracking and severity levels
- **Rate limiting and cooldowns** per alert type to prevent spam

### Security
- **Session authentication is on by default.** The installer prompts for a password or generates one and prints it once. Set `ALLSKY_WEB_AUTH=0` in `/etc/allsky-web/env` only on a trusted LAN
- bcrypt password hashing
- **Upload testing** — validate remote-web, remote-server, and local-web upload configurations

## What the installer does

1. Installs OS packages (Python 3, Node.js, OpenCV, libcamera, fonts)
2. Compiles the Allsky capture binary (`src/`)
3. Builds `sunwait` sunrise/sunset calculator
4. Creates Python venv for Allsky's overlay modules (Pillow, ephem, astral, etc.)
5. Creates Python venv for the web backend (FastAPI, uvicorn, httpx, etc.)
6. Builds the React frontend (Vite + Tailwind)
7. Copies overlay templates, module pipeline configs, and fonts
8. Sets up `allsky.service` and `allsky-web.service` as systemd units
9. Configures sudoers for service control, reboot, and camera detection
10. Starts everything and prints the URL

**First install: ~15 minutes** on a Pi 3B.

## Architecture

```
allsky.sh, scripts/, src/     # camera capture pipeline (C++ binary + bash)
backend/                      # FastAPI + uvicorn (single web server, no PHP/lighttpd)
  app/allsky/                 # filesystem adapters (images, settings, logs)
  app/notify/                 # meteor detector, focus analyzer, rain detector,
                              # ADS-B tracker, satellite predictor, notification channels
  app/routers/                # REST + WebSocket endpoints (auth, settings, images,
                              # system, maintenance, notifications, alerts)
frontend/                     # React + Tailwind + Konva
  src/routes/                 # Dashboard, Gallery, Settings, OverlayEditor,
                              # MaskEditor, Notifications, Maintenance, Alerts, etc.
html/allsky/                  # artefact dirs (keograms, startrails, videos — populated at runtime)
config_repo/                  # default overlay templates, module pipeline configs
```

## Configuration

All configuration is done through the web UI. Advanced settings in `/etc/allsky-web/env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ALLSKY_HOME` | *(auto-detected)* | Path to allsky installation |
| `ALLSKY_WEB_HOST` | `0.0.0.0` | Listen address |
| `ALLSKY_WEB_PORT` | `8000` | Listen port |
| `ALLSKY_WEB_AUTH` | `1` | Set to `0` to disable the login |
| `ALLSKY_WEB_USER` | `admin` | Username for auth |
| `ALLSKY_WEB_PASS_HASH` | *(set by installer)* | bcrypt hash of the password |
| `ALLSKY_WEB_FORWARDED_ALLOW_IPS` | *(unset)* | Reverse-proxy address allowed to set X-Forwarded-*. `*` is ignored |
| `ALLSKY_WEB_SECRET` | *(auto-generated)* | Session signing key |
| `ALLSKY_WEB_CONFIG` | *(set by installer)* | Path to web config directory |
| `ALLSKY_WEB_DATA` | `/var/lib/allsky-web` | Data directory for alert DB, notification configs |

## License

GPL-3.0 (same as upstream Allsky)
