# allsky-web

A full fork of the [Allsky](https://github.com/AllskyTeam/allsky) sky camera project with a modern, mobile-first web interface replacing the legacy PHP UI.

**One install, everything works** — camera capture backend + modern React/FastAPI web UI.

## Features

- **Live view** via WebSocket push (no polling)
- **Dashboard** with CPU temp, disk, memory, load, camera status, focus quality
- **Image gallery** with date filtering, EXIF metadata, lightbox with keyboard nav
- **Settings editor** with schema-driven forms, validation, dependency awareness
- **Visual mask editor** (Konva) with draw/erase, undo/redo, brush size
- **Keograms & startrails** viewer with full-screen overlay
- **Meteor/streak detection** with Telegram/Discord/Email/ntfy alerts
- **Focus monitoring** with calibration and cloud-proof hysteresis
- **System control**: start/stop/restart camera, log viewer
- **Dark theme** designed for nighttime use (amber accent preserves night vision)

## Quick start

```bash
# Clone and install (one command does everything)
git clone https://github.com/mucoucah/allsky.git
cd allsky
sudo ./install.sh
```

That's it. The installer will:
1. Install OS packages (Python, Node, OpenCV, libcamera, lighttpd)
2. Compile the Allsky capture binary
3. Set up the camera backend service
4. Build and install the modern web UI
5. Start everything

**First install takes 10-20 minutes** on a Pi 3B (compiling + pip packages).

Then open: `http://<your-pi-ip>:8000`

## Requirements

- Raspberry Pi 3B or newer
- Raspberry Pi OS (Bookworm 64-bit recommended)
- A supported camera (RPi camera module, IMX462, ZWO, etc.)
- Internet connection (for package installation)

## After installation

1. **Configure your camera** in the Settings page
2. **Start capture**: `sudo systemctl start allsky`
3. **Set up notifications** (optional): go to Notifications, add Telegram/Discord/Email channels
4. **Calibrate focus**: go to Notifications > Focus, click "Set current as in-focus baseline"

## Architecture

```
allsky.sh, scripts/, src/     # upstream camera capture (untouched)
backend/                      # FastAPI web server
  app/allsky/                 # filesystem adapters (paths, settings, status)
  app/notify/                 # meteor detector, focus analyzer, channels
  app/routers/                # REST + WebSocket endpoints
frontend/                     # React + Tailwind + Konva
  src/routes/                 # Dashboard, Gallery, Settings, MaskEditor, etc.
```

The web backend reads/writes the same files the capture pipeline uses
(`config/settings.json`, `tmp/image.jpg`, `images/YYYYMMDD/`, etc.)
and delegates setting changes to Allsky's own `scripts/makeChanges.sh`.

## Development

```bash
# Backend (auto-reload)
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
ALLSKY_HOME=/path/to/allsky uvicorn app.main:app --reload --host 0.0.0.0

# Frontend (Vite dev server, proxies /api to :8000)
cd frontend
npm install
npm run dev
```

## Useful commands

```bash
sudo systemctl status allsky        # camera service
sudo systemctl status allsky-web    # web UI service
sudo systemctl restart allsky-web   # restart web UI
sudo journalctl -u allsky-web -f    # web UI logs
sudo journalctl -u allsky -f        # camera logs
```

## Configuration

Edit `/etc/allsky-web/env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ALLSKY_HOME` | *(auto-detected)* | Path to allsky installation |
| `ALLSKY_WEB_HOST` | `0.0.0.0` | Listen address |
| `ALLSKY_WEB_PORT` | `8000` | Listen port |
| `ALLSKY_WEB_USER` | *(empty)* | Username for auth (empty = no auth) |
| `ALLSKY_WEB_PASS_HASH` | *(empty)* | bcrypt hash of password |

## License

GPL-3.0 (same as upstream Allsky)
