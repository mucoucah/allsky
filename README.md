# allsky-web

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

- **Live view** via WebSocket push (no polling)
- **Setup wizard** — auto-detects camera, configures, starts capture
- **Dashboard** with CPU temp, disk, memory, camera status, focus quality, start/stop buttons
- **Image gallery** with date filtering, EXIF metadata, lightbox
- **Settings editor** with validation, dependency awareness, audit trail
- **Visual mask editor** (Konva) with draw/erase, undo/redo
- **Keograms & startrails** viewer with full-screen overlay
- **Meteor/streak detection** with satellite/plane discrimination
- **Focus monitoring** with calibration and cloud-proof hysteresis
- **Multi-channel alerts**: Telegram, Discord, Email, ntfy.sh, webhook
- **System control**: start/stop/restart camera, log viewer — all from the browser
- **Dark theme** with amber accent (preserves night vision)

## What the installer does

1. Installs OS packages (Python, Node, OpenCV, libcamera)
2. Compiles the Allsky capture binary
3. Sets up camera backend + web UI as systemd services
4. Builds the React frontend
5. Starts everything and prints the URL

**First install: ~15 minutes** on a Pi 3B.

## Architecture

```
allsky.sh, scripts/, src/     # camera capture pipeline
backend/                      # FastAPI + uvicorn (single web server, no PHP/lighttpd)
  app/allsky/                 # filesystem adapters
  app/notify/                 # meteor detector, focus analyzer, notification channels
  app/routers/                # REST + WebSocket endpoints
frontend/                     # React + Tailwind + Konva
html/allsky/                  # artefact dirs (keograms, startrails, videos — populated at runtime)
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

## License

GPL-3.0 (same as upstream Allsky)
