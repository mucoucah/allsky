# allsky-web

A modern web interface for the [Allsky](https://github.com/AllskyTeam/allsky)
sky-camera project. Drop-in replacement for the legacy PHP UI — leaves the
upstream capture pipeline (`allsky.sh`, `capture_RPi`, `saveImage.sh`,
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
