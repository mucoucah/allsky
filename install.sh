#!/bin/bash
# allsky-web installer (Raspberry Pi OS Bookworm / Bullseye 64-bit).
#
# Usage:
#   sudo ./install.sh                     # auto-detects ALLSKY_HOME
#   sudo ./install.sh /home/pi/allsky     # explicit path
#
# Idempotent: safe to re-run after pulling new code. It does NOT touch the
# upstream Allsky installation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_PREFIX="/opt/allsky-web"
DATA_DIR="/var/lib/allsky-web"
SERVICE_USER="allskyweb"
ENV_FILE="/etc/allsky-web/env"
NODE_MIN_MAJOR=18

cyan()  { printf "\033[36m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$*"; }

if [[ $EUID -ne 0 ]]; then
  red "Please run with sudo:"
  red "  sudo ./install.sh"
  red "  sudo ./install.sh /path/to/allsky"
  exit 1
fi

# ── Find ALLSKY_HOME ────────────────────────────────────────────
# Priority: 1) first CLI argument, 2) existing env file, 3) auto-detect.

if [[ $# -ge 1 && -n "${1:-}" ]]; then
  ALLSKY_HOME="$1"
elif [[ -f "${ENV_FILE}" ]]; then
  # Read from existing env file if we're re-running.
  ALLSKY_HOME="$(grep -m1 '^ALLSKY_HOME=' "${ENV_FILE}" | cut -d= -f2- || true)"
fi

if [[ -z "${ALLSKY_HOME:-}" ]]; then
  # Auto-detect: search common locations.
  REAL_USER="${SUDO_USER:-pi}"
  SEARCH_PATHS=(
    "/home/${REAL_USER}/allsky"
    "/home/pi/allsky"
    "/home/allsky/allsky"
    "/opt/allsky"
  )
  # Also try every user home.
  for d in /home/*/allsky; do
    [[ -d "$d" ]] && SEARCH_PATHS+=("$d")
  done
  for p in "${SEARCH_PATHS[@]}"; do
    if [[ -f "${p}/variables.sh" ]]; then
      ALLSKY_HOME="$p"
      break
    fi
  done
fi

if [[ -z "${ALLSKY_HOME:-}" ]]; then
  red "Could not find an Allsky installation. Searched:"
  for p in "${SEARCH_PATHS[@]}"; do
    red "  $p"
  done
  echo ""
  red "Please pass the path explicitly:"
  red "  sudo ./install.sh /path/to/allsky"
  exit 1
fi

# ── Verify upstream Allsky ───────────────────────────────────────

cyan "==> Checking upstream Allsky at ${ALLSKY_HOME}"
if [[ ! -d "${ALLSKY_HOME}" ]]; then
  red "Directory not found: ${ALLSKY_HOME}"
  red "Pass the correct path: sudo ./install.sh /path/to/allsky"
  exit 1
fi
if [[ ! -f "${ALLSKY_HOME}/variables.sh" ]]; then
  red "${ALLSKY_HOME} does not look like an Allsky installation (no variables.sh)."
  exit 1
fi
ALLSKY_VER="$(head -1 "${ALLSKY_HOME}/version" 2>/dev/null || echo 'unknown')"
green "    Found Allsky ${ALLSKY_VER} at ${ALLSKY_HOME}"

# ── Create service user ──────────────────────────────────────────

cyan "==> Creating service user ${SERVICE_USER}"
if ! id -u "${SERVICE_USER}" &>/dev/null; then
  useradd --system --create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
  green "    Created."
else
  green "    Already exists."
fi
# Grant read access to Allsky's files (images, config, tmp).
ALLSKY_GROUP="$(stat -c '%G' "${ALLSKY_HOME}")"
usermod -a -G "${ALLSKY_GROUP}" "${SERVICE_USER}" 2>/dev/null || true

# ── OS packages ──────────────────────────────────────────────────

cyan "==> Installing OS packages"
apt-get update -qq

# Core packages. rsync might not be pre-installed on Lite images.
apt-get install -y -qq python3-venv python3-dev python3-pip rsync curl || true

# OpenCV native deps (for ARM wheels or source build):
apt-get install -y -qq \
  libopenjp2-7 libatlas-base-dev libhdf5-dev \
  2>/dev/null || true
# libtiff name varies: libtiff6 (Bookworm) vs libtiff5 (Bullseye).
apt-get install -y -qq libtiff6 2>/dev/null || \
  apt-get install -y -qq libtiff5 2>/dev/null || true

# Node.js — need >= 18.
if command -v node &>/dev/null; then
  NODE_VER="$(node -v | sed 's/^v//' | cut -d. -f1)"
  if [[ "${NODE_VER}" -ge ${NODE_MIN_MAJOR} ]]; then
    green "    Node.js $(node -v) OK."
    _install_node=false
  else
    yellow "    Node.js v${NODE_VER} is too old (need >= ${NODE_MIN_MAJOR})."
    _install_node=true
  fi
else
  yellow "    Node.js not found."
  _install_node=true
fi
if [[ "${_install_node}" == "true" ]]; then
  cyan "    Installing Node.js ${NODE_MIN_MAJOR} via NodeSource..."
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MIN_MAJOR}.x" | bash - 2>/dev/null
  apt-get install -y -qq nodejs
  green "    Installed Node.js $(node -v)."
fi

# ── Copy source to install prefix ────────────────────────────────

cyan "==> Copying source to ${INSTALL_PREFIX}"
mkdir -p "${INSTALL_PREFIX}"
rsync -a --delete \
  --exclude __pycache__ --exclude '*.pyc' \
  --exclude node_modules --exclude .venv --exclude dist \
  --exclude .git \
  "${SCRIPT_DIR}/backend/"  "${INSTALL_PREFIX}/backend/"
rsync -a --delete \
  --exclude node_modules --exclude dist \
  --exclude .git \
  "${SCRIPT_DIR}/frontend/" "${INSTALL_PREFIX}/frontend/"
rsync -a "${SCRIPT_DIR}/deploy/" "${INSTALL_PREFIX}/deploy/"
green "    Done."

# ── Python venv + deps ───────────────────────────────────────────

cyan "==> Creating Python virtualenv + installing dependencies"
VENV="${INSTALL_PREFIX}/backend/.venv"
if [[ ! -d "${VENV}" ]]; then
  python3 -m venv "${VENV}"
fi
"${VENV}/bin/pip" install --quiet --upgrade pip wheel setuptools 2>&1 | tail -1 || true
cyan "    Installing Python packages (this may take several minutes on first run)..."
"${VENV}/bin/pip" install --quiet "${INSTALL_PREFIX}/backend" 2>&1 | tail -3 || {
  red "    pip install failed. Retrying with verbose output..."
  "${VENV}/bin/pip" install "${INSTALL_PREFIX}/backend"
}
green "    Python deps installed."

# ── Frontend build ───────────────────────────────────────────────

cyan "==> Building React frontend"
pushd "${INSTALL_PREFIX}/frontend" >/dev/null
# npm ci needs a lockfile; fall back to npm install which generates one.
npm install --prefer-offline 2>&1 | tail -3 || npm install
npm run build 2>&1 | tail -5
popd >/dev/null
if [[ ! -f "${INSTALL_PREFIX}/frontend/dist/index.html" ]]; then
  red "    Frontend build failed — dist/index.html not found."
  red "    Check npm / vite errors above."
  exit 1
fi
green "    Frontend built to ${INSTALL_PREFIX}/frontend/dist"

# ── Data directory ───────────────────────────────────────────────

cyan "==> Setting ownership"
mkdir -p "${DATA_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${DATA_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_PREFIX}"

# ── Environment file ─────────────────────────────────────────────

cyan "==> Writing /etc/allsky-web/env"
mkdir -p /etc/allsky-web
if [[ ! -f "${ENV_FILE}" ]]; then
  SECRET="$(head -c 32 /dev/urandom | base64 | tr -d '=+/' | head -c 44)"
  cat >"${ENV_FILE}" <<ENVEOF
ALLSKY_HOME=${ALLSKY_HOME}
ALLSKY_WEB_DATA=${DATA_DIR}
ALLSKY_WEB_SECRET=${SECRET}
ALLSKY_WEB_HOST=0.0.0.0
ALLSKY_WEB_PORT=8000
ALLSKY_WEB_USER=
ALLSKY_WEB_PASS_HASH=
ENVEOF
  chmod 640 "${ENV_FILE}"
  chown root:"${SERVICE_USER}" "${ENV_FILE}"
  green "    Created with random secret."
else
  # Update ALLSKY_HOME if it changed.
  if ! grep -q "^ALLSKY_HOME=${ALLSKY_HOME}$" "${ENV_FILE}"; then
    sed -i "s|^ALLSKY_HOME=.*|ALLSKY_HOME=${ALLSKY_HOME}|" "${ENV_FILE}"
    green "    Updated ALLSKY_HOME in existing env file."
  else
    green "    Already exists, left unchanged."
  fi
fi

# ── systemd ──────────────────────────────────────────────────────

cyan "==> Installing systemd unit"
cat >/etc/systemd/system/allsky-web.service <<SVCEOF
[Unit]
Description=Allsky modern web interface (FastAPI)
After=network-online.target allsky.service
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
EnvironmentFile=-${ENV_FILE}
WorkingDirectory=${INSTALL_PREFIX}/backend
ExecStart=${INSTALL_PREFIX}/backend/.venv/bin/uvicorn app.main:app \
    --host \${ALLSKY_WEB_HOST} --port \${ALLSKY_WEB_PORT} --proxy-headers \
    --forwarded-allow-ips='*'
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true

[Install]
WantedBy=multi-user.target
SVCEOF
systemctl daemon-reload
systemctl enable allsky-web.service
green "    Enabled allsky-web.service."

# ── sudoers ──────────────────────────────────────────────────────

cyan "==> Installing sudoers drop-in"
cat >/etc/sudoers.d/allsky-web <<SUDOEOF
${SERVICE_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl start allsky.service
${SERVICE_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl stop allsky.service
${SERVICE_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart allsky.service
SUDOEOF
chmod 0440 /etc/sudoers.d/allsky-web
if ! visudo -cf /etc/sudoers.d/allsky-web >/dev/null 2>&1; then
  red "    Warning: sudoers syntax check failed. Service control may not work."
else
  green "    Installed."
fi

# ── Start the service ────────────────────────────────────────────

cyan "==> Starting allsky-web"
systemctl start allsky-web.service || {
  red "    Failed to start. Check: sudo journalctl -u allsky-web -n 30"
}

# ── Done ─────────────────────────────────────────────────────────

# Wait a moment for uvicorn to bind.
sleep 2
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
PORT="$(grep -m1 '^ALLSKY_WEB_PORT=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2 || echo 8000)"

echo ""
green "================================================================="
green "  allsky-web installed and started!"
green "================================================================="
echo ""
if systemctl is-active --quiet allsky-web.service; then
  green "  Service is running."
  echo ""
  cyan  "  Open in your browser:"
  echo  "    http://${IP:-<pi-ip>}:${PORT}"
else
  yellow "  Service may not have started. Check logs:"
  echo   "    sudo journalctl -u allsky-web -n 50"
fi
echo ""
cyan  "  Useful commands:"
echo  "    sudo systemctl status allsky-web"
echo  "    sudo systemctl restart allsky-web"
echo  "    sudo journalctl -u allsky-web -f"
echo ""
cyan  "  Config: ${ENV_FILE}"
cyan  "  Allsky: ${ALLSKY_HOME}"
echo ""
