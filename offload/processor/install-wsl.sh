#!/bin/bash
# Install the Allsky processor and the web UI inside WSL2 Ubuntu.
# No Docker. ffmpeg comes from apt so it can see the Windows NVIDIA driver.
#
# Usage (inside Ubuntu, from the repo root):
#   sudo ./offload/processor/install-wsl.sh
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo from the repo root." >&2
  exit 1
fi

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
REAL_USER="${SUDO_USER:-${USER}}"
DATA=/srv/allsky/data
INCOMING=/srv/allsky/incoming
TOPI=/srv/allsky/to-pi
PREFIX=/opt/allsky-processor
WEB=/opt/allsky-web

apt-get update -qq
apt-get install -y python3 python3-venv python3-pip \
  ffmpeg openssh-server rsync

mkdir -p "${INCOMING}/status" "${TOPI}" \
  "${DATA}/images" "${DATA}/tmp" "${DATA}/config" \
  "${DATA}/html/allsky/meteors" "${PREFIX}" "${WEB}/backend" "${WEB}/config"
chown -R "${REAL_USER}:${REAL_USER}" /srv/allsky "${PREFIX}" "${WEB}"

if ! id allsky >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash allsky
fi
usermod -a -G "${REAL_USER}" allsky || true
chown -R allsky:allsky "${INCOMING}" "${TOPI}"

install -d -o allsky -g allsky -m 0700 /home/allsky/.ssh
if [[ ! -f /home/allsky/.ssh/authorized_keys ]]; then
  touch /home/allsky/.ssh/authorized_keys
  chown allsky:allsky /home/allsky/.ssh/authorized_keys
  chmod 0600 /home/allsky/.ssh/authorized_keys
fi

rm -rf "${PREFIX}/offload"
cp -a "${REPO}/offload" "${PREFIX}/offload"
rm -rf "${WEB}/backend/app"
cp -a "${REPO}/backend/app" "${WEB}/backend/app"
cp "${REPO}/backend/pyproject.toml" "${WEB}/backend/pyproject.toml"
cp "${REPO}/backend/run-web.sh" "${WEB}/backend/run-web.sh"
chmod 0755 "${WEB}/backend/run-web.sh"

if [[ ! -d "${PREFIX}/.venv" ]]; then
  python3 -m venv "${PREFIX}/.venv"
fi
"${PREFIX}/.venv/bin/pip" install --upgrade pip
"${PREFIX}/.venv/bin/pip" install "numpy>=1.26" "opencv-python-headless>=4.9"

if [[ ! -d "${WEB}/backend/.venv" ]]; then
  python3 -m venv "${WEB}/backend/.venv"
fi
"${WEB}/backend/.venv/bin/pip" install --upgrade pip
"${WEB}/backend/.venv/bin/pip" install "${WEB}/backend"

if [[ ! -f /srv/allsky/offload.json ]]; then
  python3 - "${REPO}" <<'PY'
import json, sys
from pathlib import Path
src = Path(sys.argv[1]) / "config" / "offload.json.example"
data = json.loads(src.read_text()) if src.is_file() else {}
data["mode"] = "capture-only"
proc = data.setdefault("processor", {})
proc["incoming_dir"] = "/srv/allsky/incoming"
proc["data_dir"] = "/srv/allsky/data"
proc["to_pi_dir"] = "/srv/allsky/to-pi"
proc.setdefault("raw_retention_days", 14)
proc.setdefault("min_free_gb", 10)
remote = data.setdefault("remote", {})
remote["path"] = "/srv/allsky/incoming"
remote["settings_path"] = "/srv/allsky/to-pi"
remote["port"] = 2222
Path("/srv/allsky/offload.json").write_text(json.dumps(data, indent=2) + "\n")
Path("/srv/allsky/data/config/offload.json").write_text(json.dumps(data, indent=2) + "\n")
PY
fi
chown "${REAL_USER}:${REAL_USER}" /srv/allsky/offload.json "${DATA}/config/offload.json" || true

mkdir -p /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/allsky.conf <<'EOF'
Port 2222
PasswordAuthentication no
PubkeyAuthentication yes
EOF

cat >/etc/systemd/system/allsky-processor.service <<EOF
[Unit]
Description=Allsky PC processor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=allsky
Group=allsky
Environment=ALLSKY_HOME=${DATA}
Environment=ALLSKY_OFFLOAD_CONFIG=/srv/allsky/offload.json
Environment=ALLSKY_BACKEND=${WEB}/backend
Environment=PYTHONPATH=${PREFIX}:${WEB}/backend
WorkingDirectory=${PREFIX}
ExecStart=${PREFIX}/.venv/bin/python -m offload.processor
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

if [[ ! -f /etc/allsky-web/env ]]; then
  mkdir -p /etc/allsky-web
  SECRET="$(head -c 32 /dev/urandom | base64 | tr -d '=+/' | head -c 44)"
  cat >/etc/allsky-web/env <<EOF
ALLSKY_HOME=${DATA}
ALLSKY_WEB_CONFIG=${DATA}/config
ALLSKY_WEB_DATA=/var/lib/allsky-web
ALLSKY_WEB_SECRET=${SECRET}
ALLSKY_WEB_HOST=0.0.0.0
ALLSKY_WEB_PORT=8000
ALLSKY_WEB_AUTH=1
ALLSKY_OFFLOAD_CONFIG=/srv/allsky/offload.json
PYTHONPATH=${PREFIX}:${WEB}/backend
EOF
fi
mkdir -p /var/lib/allsky-web
chown -R "${REAL_USER}:${REAL_USER}" /var/lib/allsky-web /etc/allsky-web || true

cat >/etc/systemd/system/allsky-web.service <<EOF
[Unit]
Description=Allsky web UI (PC)
After=network-online.target allsky-processor.service

[Service]
Type=simple
User=allsky
Group=allsky
EnvironmentFile=-/etc/allsky-web/env
WorkingDirectory=${WEB}/backend
ExecStart=${WEB}/backend/run-web.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

chown -R allsky:allsky /srv/allsky /var/lib/allsky-web
chmod 644 /etc/allsky-web/env || true
chmod -R a+rX "${WEB}" "${PREFIX}" || true

# WSL systemd must be enabled in /etc/wsl.conf before these units start.
if [[ -d /run/systemd/system ]]; then
  systemctl daemon-reload
  systemctl enable ssh allsky-processor.service allsky-web.service
  systemctl restart ssh || systemctl start ssh || true
  systemctl restart allsky-processor.service || true
  systemctl restart allsky-web.service || true
else
  echo "systemd is not running inside WSL. Add systemd=true to /etc/wsl.conf, then: wsl --shutdown"
fi

echo
echo "Processor code: ${PREFIX}"
echo "Web UI env:     /etc/allsky-web/env"
echo "Incoming:       ${INCOMING}"
echo "Raw frames:     processor.raw_retention_days (default 14) deletes capture JPEGs only."
echo "Disk guard:     processor.min_free_gb (default 10) pauses raw storage below that many GB."
echo "Open the UI at http://<pc-lan-ip>:8000 after the frontend is built."
if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is not installed. Install Node 20, then:"
  echo "  cd ${REPO}/frontend && npm install && npm run build"
  echo "  sudo cp -a dist ${WEB}/frontend/dist"
else
  if [[ -f ${REPO}/frontend/package.json ]]; then
    (cd "${REPO}/frontend" && npm install && npm run build)
    mkdir -p "${WEB}/frontend"
    rm -rf "${WEB}/frontend/dist"
    cp -a "${REPO}/frontend/dist" "${WEB}/frontend/dist"
  fi
fi
echo "Check NVENC: ffmpeg -hide_banner -encoders | grep nvenc"
chmod -R a+rX "${WEB}" "${PREFIX}" || true
echo "Networking steps are in the README section 'Offload processing to a PC'."
