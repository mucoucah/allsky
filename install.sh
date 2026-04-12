#!/bin/bash
# allsky-web installer (Raspberry Pi OS Bookworm / Bullseye 64-bit).
#
# Idempotent: safe to re-run after pulling new code. It does NOT touch the
# upstream Allsky installation in $ALLSKY_HOME.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ALLSKY_HOME="${ALLSKY_HOME:-/home/${SUDO_USER:-pi}/allsky}"
INSTALL_PREFIX="${INSTALL_PREFIX:-/opt/allsky-web}"
DATA_DIR="${ALLSKY_WEB_DATA:-/var/lib/allsky-web}"
SERVICE_USER="${ALLSKY_WEB_USER_NAME:-allskyweb}"
ENV_FILE="/etc/allsky-web/env"
NODE_MIN_MAJOR=18

cyan()  { printf "\033[36m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }

if [[ $EUID -ne 0 ]]; then
  red "Please run with sudo: sudo ./install.sh"
  exit 1
fi

# ── Verify upstream Allsky ───────────────────────────────────────

cyan "==> Checking upstream Allsky at ${ALLSKY_HOME}"
if [[ ! -d "${ALLSKY_HOME}" ]]; then
  red "Upstream Allsky not found at ${ALLSKY_HOME}."
  red "Install it first (https://github.com/AllskyTeam/allsky) or set ALLSKY_HOME."
  exit 1
fi
if [[ ! -f "${ALLSKY_HOME}/variables.sh" ]]; then
  red "${ALLSKY_HOME} does not look like an Allsky installation (no variables.sh)."
  exit 1
fi
green "    Found $(head -1 "${ALLSKY_HOME}/version" 2>/dev/null || echo 'unknown version')."

# ── Create service user ──────────────────────────────────────────

cyan "==> Creating service user ${SERVICE_USER}"
if ! id -u "${SERVICE_USER}" &>/dev/null; then
  useradd --system --create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
  green "    Created."
else
  green "    Already exists."
fi
ALLSKY_GROUP="$(stat -c '%G' "${ALLSKY_HOME}")"
usermod -a -G "${ALLSKY_GROUP}" "${SERVICE_USER}" 2>/dev/null || true

# ── OS packages ──────────────────────────────────────────────────

cyan "==> Installing OS packages"
apt-get update -qq
# OpenCV build deps (for opencv-python-headless wheel on ARM if no prebuilt):
apt-get install -y -q python3-venv python3-dev python3-pip \
  libopenjp2-7 libtiff6 libatlas-base-dev libhdf5-dev \
  2>/dev/null || true

# Node.js — need >= 18. Check if available, install via NodeSource if not.
if command -v node &>/dev/null; then
  NODE_VER="$(node -v | sed 's/^v//' | cut -d. -f1)"
  if [[ "${NODE_VER}" -lt ${NODE_MIN_MAJOR} ]]; then
    red "    Node.js v${NODE_VER} is too old (need >= ${NODE_MIN_MAJOR}). Installing newer version."
    _install_node=true
  else
    green "    Node.js v$(node -v) OK."
    _install_node=false
  fi
else
  _install_node=true
fi
if [[ "${_install_node}" == "true" ]]; then
  cyan "    Installing Node.js ${NODE_MIN_MAJOR} via NodeSource..."
  if command -v curl &>/dev/null; then
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MIN_MAJOR}.x" | bash -
  else
    apt-get install -y -q curl
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MIN_MAJOR}.x" | bash -
  fi
  apt-get install -y -q nodejs
  green "    Installed Node.js $(node -v)."
fi

# ── Copy source to install prefix ────────────────────────────────

cyan "==> Copying source to ${INSTALL_PREFIX}"
mkdir -p "${INSTALL_PREFIX}"
rsync -a --delete \
  --exclude __pycache__ --exclude '*.pyc' \
  --exclude node_modules --exclude .venv --exclude dist \
  "${SCRIPT_DIR}/backend/"  "${INSTALL_PREFIX}/backend/"
rsync -a --delete \
  --exclude node_modules --exclude dist \
  "${SCRIPT_DIR}/frontend/" "${INSTALL_PREFIX}/frontend/"
# Copy deploy artefacts.
rsync -a "${SCRIPT_DIR}/deploy/" "${INSTALL_PREFIX}/deploy/"
green "    Done."

# ── Python venv + deps ───────────────────────────────────────────

cyan "==> Creating Python virtualenv + installing dependencies"
VENV="${INSTALL_PREFIX}/backend/.venv"
if [[ ! -d "${VENV}" ]]; then
  python3 -m venv "${VENV}"
fi
"${VENV}/bin/pip" install --quiet --upgrade pip wheel setuptools
"${VENV}/bin/pip" install --quiet -e "${INSTALL_PREFIX}/backend"
green "    Python deps installed."

# ── Frontend build ───────────────────────────────────────────────

cyan "==> Building React frontend"
pushd "${INSTALL_PREFIX}/frontend" >/dev/null
npm ci --prefer-offline 2>/dev/null || npm install
npm run build
popd >/dev/null
green "    Frontend built to ${INSTALL_PREFIX}/frontend/dist"

# ── Data directory ───────────────────────────────────────────────

cyan "==> Creating data directory ${DATA_DIR}"
mkdir -p "${DATA_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${DATA_DIR}"
# The backend writes to DATA_DIR; the frontend dist is read-only.
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
# Listen on all interfaces so you can reach the UI from another device.
ALLSKY_WEB_HOST=0.0.0.0
ALLSKY_WEB_PORT=8000
# Set these to require login (empty = no auth, LAN-trusted mode).
# Generate a hash:  python3 -c "from passlib.hash import bcrypt; print(bcrypt.hash('YOUR-PASS'))"
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
ExecStart=${INSTALL_PREFIX}/backend/.venv/bin/uvicorn app.main:app \\
    --host \${ALLSKY_WEB_HOST} --port \${ALLSKY_WEB_PORT} --proxy-headers \\
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
# allsky-web: allow service control only
${SERVICE_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl start allsky.service
${SERVICE_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl stop allsky.service
${SERVICE_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart allsky.service
SUDOEOF
chmod 0440 /etc/sudoers.d/allsky-web
visudo -cf /etc/sudoers.d/allsky-web
green "    Installed."

# ── Done ─────────────────────────────────────────────────────────

echo ""
green "================================================================="
green "  allsky-web installed successfully!"
green "================================================================="
echo ""
cyan  "  Start the service:"
echo  "    sudo systemctl start allsky-web"
echo ""
cyan  "  Then open in your browser:"
echo  "    http://$(hostname -I 2>/dev/null | awk '{print $1}'):8000"
echo ""
cyan  "  The UI serves directly from FastAPI — no lighttpd config needed."
cyan  "  (Optional: use deploy/lighttpd-allskyweb.conf for a reverse proxy.)"
echo ""
cyan  "  To enable authentication, edit ${ENV_FILE}"
echo ""
