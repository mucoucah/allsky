# allsky-web v1.14.0

A full fork of the [Allsky](https://github.com/AllskyTeam/allsky) sky camera project with a modern, mobile-first web interface. No PHP, no lighttpd — just FastAPI + React.

**One install, everything works.** Camera capture backend + modern web UI.

## Quick start

```bash
git clone https://github.com/mucoucah/allsky.git
cd allsky
sudo ./install.sh
```

Open `http://<your-pi-ip>:8000` — the setup wizard walks you through camera detection and configuration. No terminal needed after install.

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
- **Optional session-based authentication** with bcrypt password hashing
- Can be disabled entirely for LAN-trusted setups by leaving `ALLSKY_WEB_USER` empty
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
| `ALLSKY_WEB_USER` | *(empty)* | Username for auth (empty = no auth) |
| `ALLSKY_WEB_PASS_HASH` | *(empty)* | bcrypt hash of password |
| `ALLSKY_WEB_SECRET` | *(auto-generated)* | Session signing key |
| `ALLSKY_WEB_CONFIG` | *(set by installer)* | Path to web config directory |
| `ALLSKY_WEB_DATA` | `/var/lib/allsky-web` | Data directory for alert DB, notification configs |

## License

GPL-3.0 (same as upstream Allsky)
