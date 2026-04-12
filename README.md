# allsky-web

A modern, mobile-first web interface for the [Allsky](https://github.com/AllskyTeam/allsky) sky camera project. Replaces the legacy PHP WebUI while keeping the core capture backend untouched.

## Features

- **Live view** via WebSocket push (no polling) with connection status
- **Dashboard** with CPU temp, disk, memory, load, camera status, focus quality
- **Image gallery** with date filtering, sort by EXIF metadata, lightbox with keyboard nav
- **Settings editor** with schema-driven forms, validation, dependency awareness, audit trail
- **Visual mask editor** (Konva) with draw/erase, undo/redo, brush size, opacity, load existing masks
- **Keograms & startrails** viewer with full-screen overlay and arrow-key navigation
- **Meteor/streak detection** (Canny + Hough + satellite discrimination) with auto-alerts
- **Focus monitoring** (variance of Laplacian) with calibration and hysteresis
- **Multi-channel notifications**: Telegram, Discord, Email, ntfy.sh, webhook
- **System control**: start/stop/restart Allsky, log tail viewer
- **Alerts panel** with acknowledgement
- **Dark theme** designed for nighttime use (amber accent to preserve night vision)

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, uvicorn, aiosqlite |
| Frontend | React 18, Vite, Tailwind CSS, react-konva |
| Detection | OpenCV (Canny/Hough), numpy |
| Notifications | httpx (async HTTP), smtplib |
| Database | SQLite (metadata, alerts, audit) |

## Requirements

- Raspberry Pi 3B or newer (64-bit OS recommended)
- Allsky v2024.x installed and capturing images
- Python 3.11+
- Node.js 18+ (installer will fetch if missing)

## Installation

```bash
# Clone the repo
git clone https://github.com/mucoucah/allsky.git allsky-web
cd allsky-web

# Run the installer (installs to /opt/allsky-web)
sudo ./install.sh

# Start the service
sudo systemctl start allsky-web

# Open in browser
# http://<pi-ip>:8000
```

The installer will:
1. Create an `allskyweb` service user
2. Install Python/Node dependencies
3. Build the React frontend
4. Create a systemd service
5. Generate a session secret

### Environment variables

Edit `/etc/allsky-web/env` to configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `ALLSKY_HOME` | `/home/pi/allsky` | Path to upstream Allsky |
| `ALLSKY_WEB_HOST` | `0.0.0.0` | Listen address |
| `ALLSKY_WEB_PORT` | `8000` | Listen port |
| `ALLSKY_WEB_USER` | *(empty)* | Username for auth (empty = no auth) |
| `ALLSKY_WEB_PASS_HASH` | *(empty)* | bcrypt hash of password |
| `ALLSKY_WEB_SECRET` | *(auto-generated)* | Session signing key |

To enable authentication:
```bash
# Generate a password hash
python3 -c "from passlib.hash import bcrypt; print(bcrypt.hash('your-password'))"

# Add to /etc/allsky-web/env
ALLSKY_WEB_USER=admin
ALLSKY_WEB_PASS_HASH=$2b$12$...
```

## Development

```bash
# Backend (auto-reload)
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --host 0.0.0.0

# Frontend (Vite dev server, proxies /api to :8000)
cd frontend
npm install
npm run dev
```

## Notification setup

Go to **Notifications** in the sidebar:

1. Click **Add channel** and configure Telegram/Discord/Email/ntfy/webhook
2. Click the test button to verify
3. Enable **Meteor detection** and adjust the minimum streak length
4. Enable **Focus monitoring** and click "Set current as in-focus baseline"

Alerts are deduplicated per day and dispatched to all enabled channels.

## Architecture

```
backend/
  app/
    allsky/    # filesystem adapters (paths, settings, status, images, masks)
    notify/    # channels, meteor detector, focus analyzer, watchers
    routers/   # FastAPI endpoints
    ws/        # WebSocket broadcaster
    main.py    # app factory + lifespan
frontend/
  src/
    routes/    # Dashboard, Gallery, Settings, MaskEditor, Keograms, etc.
    components/# Layout, Tile, StatusPill, SettingField
    hooks/     # useLiveSocket, useElementSize
    lib/       # api client, depends parser, validator
deploy/        # systemd unit, sudoers, lighttpd config
```

The backend **never modifies** the Allsky capture pipeline. It reads/writes the same files Allsky uses (`config/settings.json`, `config/overlay/images/*.png`, `tmp/image.jpg`, etc.) and delegates setting changes to Allsky's own `scripts/makeChanges.sh`.

## Uninstall

```bash
sudo ./uninstall.sh
```

Removes the service, user, installed files, and data directory. Does not touch upstream Allsky.

## License

Same as the upstream Allsky project (GPL-3.0).
`flow-runner.py`) completely untouched and integrates purely through the same
filesystem locations Allsky already reads and writes.

## Goals

- Clean, mobile-first dark theme tuned for night use
- Real-time live view via WebSocket push (no JPEG polling)
- In-browser mask editor (paint / erase, atomically writes a PNG into
  `${ALLSKY_HOME}/config/overlay/images/`)
- Filterable image gallery backed by a SQLite metadata index
- Schema-driven settings editor with validation, grouped by tab
- Keograms / startrails / alerts / system status all on one dashboard
- Tight, auditable service-control surface (gated `systemctl` via sudoers)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (React + Tailwind, dark)                           │
│   ▲  WS binary frames + JSON meta            HTTP /api/...  │
│   │                                                         │
└───┼─────────────────────────────────────────────────────────┘
    │
┌───┴─────────────────────────────────────────────────────────┐
│  uvicorn → FastAPI (allsky-web)                             │
│  ── routers: live, system, settings, images, masks, ...     │
│  ── inotify watcher → broadcaster → WS clients              │
│  ── SQLite (metadata, alerts, settings audit)               │
└───┬─────────────────────────────────────────────────────────┘
    │  filesystem only — no IPC, no daemons, no recompiles
┌───┴─────────────────────────────────────────────────────────┐
│  Upstream Allsky (~/allsky/)                                │
│  ├── tmp/image.jpg          ← we read on inotify trigger    │
│  ├── config/settings.json   ← read/write via makeChanges.sh │
│  ├── config/options.json    ← schema for the settings UI    │
│  ├── config/status.json     ← Allsky's own state            │
│  ├── config/overlay/images/ ← masks live here               │
│  ├── images/YYYYMMDD/       ← gallery source                │
│  └── html/allsky/{keograms,startrails}/                     │
└─────────────────────────────────────────────────────────────┘
```

## Layout

```
backend/                FastAPI app
├── pyproject.toml
└── app/
    ├── main.py         app factory + lifespan
    ├── config.py       env-driven settings
    ├── db.py           SQLite helpers (aiosqlite)
    ├── allsky/         adapters for the upstream filesystem
    │   ├── paths.py        mirrors variables.sh
    │   ├── settings.py     parses options.json + values
    │   ├── status.py       status.json + messages.txt + version
    │   ├── system.py       psutil + thermal zone
    │   ├── images.py       gallery scanning + EXIF
    │   ├── masks.py        write/read mask PNGs
    │   ├── service.py      systemctl + makeChanges.sh
    │   └── watcher.py      inotify on tmp/image.jpg → broadcaster
    ├── routers/        HTTP + WS endpoints
    └── ws/manager.py   per-client send queues, fan-out

frontend/               React + Vite + Tailwind
├── package.json
└── src/
    ├── main.tsx
    ├── App.tsx                  routes
    ├── components/Layout.tsx    sidebar / bottom-nav, brand
    ├── components/Tile.tsx      dashboard tile
    ├── components/StatusPill.tsx
    ├── hooks/useLiveSocket.ts   WebSocket client
    ├── lib/api.ts               typed fetch wrapper
    └── routes/
        ├── Dashboard.tsx        live view + system tiles + messages
        ├── Gallery.tsx          date / sort / lazy thumbs
        ├── Settings.tsx         schema-driven, read-only in M1
        ├── MaskEditor.tsx       canvas paint → PUT mask PNG
        ├── Keograms.tsx
        ├── Alerts.tsx
        └── System.tsx           service control + system tiles

deploy/
├── allsky-web.service           systemd unit
├── sudoers.d/allsky-web         gated systemctl rules
└── lighttpd-allskyweb.conf      reverse proxy + SPA fallback

install.sh                       sudoer one-shot installer
```

## Development

```bash
# Backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
ALLSKY_HOME=$HOME/allsky uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev    # → http://localhost:5173, proxies /api to :8000
```

The dev server runs on port 5173 and proxies `/api` (and the WebSocket) to
the FastAPI process on 8000, so you can run the legacy PHP WebUI on its
existing port without any conflict during the cutover.

## Production install

```bash
sudo ./install.sh
sudo systemctl start allsky-web
```

The installer:

1. Creates a dedicated `allskyweb` system user.
2. Copies the project to `/opt/allsky-web/`.
3. Builds the React bundle to `frontend/dist/`.
4. Creates `/var/lib/allsky-web/` for the SQLite DB and a random session secret
   in `/etc/allsky-web/env`.
5. Installs the systemd unit and a sudoers drop-in that allows
   `systemctl {start,stop,restart} allsky.service` only — nothing else.

Then drop `deploy/lighttpd-allskyweb.conf` into
`/etc/lighttpd/conf-available/` and enable it; or for a LAN-only setup just
visit `http://<pi-host>:8000` directly.

## Auth

Auth is **off by default** for trusted LAN use. To enable:

```bash
python3 -c "from passlib.hash import bcrypt; print(bcrypt.hash('your-password'))"
# add ALLSKY_WEB_USER=admin and ALLSKY_WEB_PASS_HASH=$2b$... to /etc/allsky-web/env
sudo systemctl restart allsky-web
```

## Roadmap

| Milestone | Status | What it adds |
|-----------|--------|--------------|
| M1 — read-only skeleton                   | done | layout, settings/values, image listing, system snapshot |
| M2 — live view via WebSocket              | done | inotify watcher, binary frames, meta channel |
| M3 — settings editor with validation      | next | PATCH /api/settings + audit log + makeChanges.sh apply |
| M4 — full gallery (search, EXIF filter)   |      | richer queries on the metadata index |
| M5 — full mask editor (Konva, undo)       |      | layered editor with history + opacity preview |
| M6 — keograms / startrails / alerts polish|      | dashboards + nightly summary digest |
| M7 — cutover & docs                       |      | retire legacy PHP UI, write upgrade guide |

## What we deliberately don't do

- We never re-implement the capture pipeline. `bin/capture_RPi`, `saveImage.sh`,
  the dark-frame and overlay modules — all stay upstream-canonical.
- We never write our own copy of `settings.json`. The DB stores only metadata
  (image index, alerts, audit). The upstream JSON file is the source of truth
  for setting values.
- We never bypass `makeChanges.sh` for settings application; it has subtle
  camera-link logic that we shouldn't reinvent.
