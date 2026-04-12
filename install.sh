#!/bin/bash
# allsky-web: unified installer for the full fork.
#
# This installs BOTH the Allsky camera capture backend AND the modern web UI.
# It replaces upstream's install.sh with a single script that does everything.
#
# Usage:
#   sudo ./install.sh
#
# What it does:
#   1. Installs OS packages (python, node, opencv deps, libcamera, etc.)
#   2. Runs upstream Allsky setup (compiles capture binary, creates services)
#   3. Installs the modern Python/React web UI alongside the legacy one
#   4. Creates a systemd service for the new web UI
#
# Re-run safe: idempotent on all steps.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export ALLSKY_HOME="${SCRIPT_DIR}"
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
  red "Please run with sudo:  sudo ./install.sh"
  exit 1
fi

# Read version from the Python package (single source of truth).
VERSION="$(grep -m1 '__version__' "${SCRIPT_DIR}/backend/app/__init__.py" | sed 's/.*"\(.*\)".*/\1/')"

echo ""
echo ""
cyan  "    ___    ____  __   _____ __ __ __  __"
cyan  "   /   |  / / / / /  / ___// //_/\\ \\/ /"
cyan  "  / /| | / / / / /   \\__ \\/ ,<    \\  / "
cyan  "/ ___ |/ / / / /___  ___/ / /| |   / /  "
cyan  "/_/  |_/_/_/ /_____/ /____/_/ |_|  /_/   "
echo ""
green "  v${VERSION}"
echo ""
cyan  "  Modern web interface for Allsky sky cameras"
cyan  "  Camera backend + FastAPI + React"
echo ""
cyan  "================================================================="
echo ""

# ── Step 1: OS packages ─────────────────────────────────────────

cyan "==> [1/6] Installing OS packages"
apt-get update -qq

# Base tools.
apt-get install -y -qq \
  python3-venv python3-dev python3-pip \
  curl rsync jq bc gawk \
  2>/dev/null || true

# Allsky's own dependencies (no lighttpd/PHP — our FastAPI replaces the legacy web UI).
apt-get install -y -qq \
  libatlas-base-dev libhdf5-dev libopenjp2-7 \
  imagemagick libcamera-apps python3-libcamera \
  uhubctl \
  2>/dev/null || true

# libtiff varies by Debian version.
apt-get install -y -qq libtiff6 2>/dev/null || \
  apt-get install -y -qq libtiff5 2>/dev/null || true

# Node.js for the frontend build.
if command -v node &>/dev/null; then
  NODE_VER="$(node -v | sed 's/^v//' | cut -d. -f1)"
  if [[ "${NODE_VER}" -ge ${NODE_MIN_MAJOR} ]]; then
    green "    Node.js $(node -v) OK."
    _install_node=false
  else
    yellow "    Node.js v${NODE_VER} too old (need >= ${NODE_MIN_MAJOR})."
    _install_node=true
  fi
else
  _install_node=true
fi
if [[ "${_install_node}" == "true" ]]; then
  cyan "    Installing Node.js ${NODE_MIN_MAJOR}..."
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MIN_MAJOR}.x" | bash - 2>/dev/null
  apt-get install -y -qq nodejs
  green "    Installed Node.js $(node -v)."
fi

green "    OS packages done."

# ── Step 2: Upstream Allsky setup ────────────────────────────────

cyan "==> [2/6] Setting up Allsky camera backend"

# Compile the capture binary if not already built, or if header needs regeneration.
if [[ -f "${ALLSKY_HOME}/src/Makefile" ]]; then

  # Generate allsky_common.h from .repo template, replacing XX_ placeholders
  # with actual file paths.  Without this, the capture binary looks for files
  # called "XX_ALLSKY_HOME_XX" etc. instead of real paths.
  HEADER_REPO="${ALLSKY_HOME}/src/include/allsky_common.h.repo"
  HEADER_OUT="${ALLSKY_HOME}/src/include/allsky_common.h"
  if [[ -f "${HEADER_REPO}" ]]; then
    cyan "    Generating allsky_common.h with correct paths..."
    sed \
      -e "s|XX_ALLSKY_HOME_XX|${ALLSKY_HOME}|g" \
      -e "s|XX_CONNECTED_CAMERAS_FILE_XX|${ALLSKY_HOME}/config/connected_cameras.txt|g" \
      -e "s|XX_RPI_CAMERA_INFO_FILE_XX|${ALLSKY_HOME}/config/RPi_cameraInfo.txt|g" \
      "${HEADER_REPO}" > "${HEADER_OUT}"
    # Force recompile since header changed.
    rm -f "${ALLSKY_HOME}/src/"*.o 2>/dev/null || true
    rm -f "${ALLSKY_HOME}/bin/capture_RPi" 2>/dev/null || true
  fi

  if [[ ! -f "${ALLSKY_HOME}/bin/capture_RPi" ]]; then
    cyan "    Installing build dependencies (libopencv, libusb)..."
    apt-get install -y -qq libopencv-dev libusb-dev libusb-1.0-0-dev \
      pkg-config g++ make git 2>/dev/null || true

    # sunwait is a git submodule in upstream allsky — clone it if missing.
    if [[ ! -f "${ALLSKY_HOME}/src/sunwait-src/sunwait.c" ]]; then
      cyan "    Cloning sunwait (sunrise/sunset calculator)..."
      rm -rf "${ALLSKY_HOME}/src/sunwait-src"
      git clone --depth 1 https://github.com/risacher/sunwait.git \
        "${ALLSKY_HOME}/src/sunwait-src" 2>&1 | tail -2 || {
        yellow "    sunwait clone failed (non-fatal — day/night detection may not work)"
      }
    fi

    cyan "    Compiling capture binary (this takes a few minutes)..."
    pushd "${ALLSKY_HOME}/src" >/dev/null
    make -j"$(nproc)" all 2>&1 | tail -10 || {
      yellow "    Capture binary build skipped or failed."
      yellow "    The web UI will still work. You can retry later from the System page."
    }
    popd >/dev/null
  fi  # end capture_RPi build
fi  # end Makefile exists

# Replace PHP convertJSON with Python version (eliminates PHP dependency).
if [[ -f "${ALLSKY_HOME}/scripts/convertJSON.py" ]]; then
  chmod +x "${ALLSKY_HOME}/scripts/convertJSON.py"
  # Create a shim so scripts calling convertJSON.php use Python instead.
  cat > "${ALLSKY_HOME}/scripts/convertJSON.php" <<'PHPSHIM'
#!/bin/bash
# PHP replaced by Python — this shim forwards all arguments.
exec "$(dirname "$0")/convertJSON.py" "$@"
PHPSHIM
  chmod +x "${ALLSKY_HOME}/scripts/convertJSON.php"
  green "    Replaced convertJSON.php with Python version."
fi

# Create essential directories that Allsky expects.
mkdir -p "${ALLSKY_HOME}"/{tmp,config,images,darks,bin,logs}
mkdir -p "${ALLSKY_HOME}/config"/{overlay/images,modules,logs}
mkdir -p "${ALLSKY_HOME}/html/allsky"/{keograms,startrails,videos}

# Copy compiled binaries.
if [[ -f "${ALLSKY_HOME}/src/capture_RPi" ]]; then
  cp "${ALLSKY_HOME}/src/capture_RPi" "${ALLSKY_HOME}/bin/"
  cp "${ALLSKY_HOME}/src/keogram" "${ALLSKY_HOME}/bin/" 2>/dev/null || true
  cp "${ALLSKY_HOME}/src/startrails" "${ALLSKY_HOME}/bin/" 2>/dev/null || true
  green "    Capture binaries installed."
fi

# Install sunwait (sunrise/sunset calculator) to PATH.
# The capture binary calls "sunwait" to determine day/night.
SUNWAIT_BIN=""
if [[ -f "${ALLSKY_HOME}/src/sunwait-src/sunwait" ]]; then
  SUNWAIT_BIN="${ALLSKY_HOME}/src/sunwait-src/sunwait"
elif [[ -f "${ALLSKY_HOME}/bin/sunwait" ]]; then
  SUNWAIT_BIN="${ALLSKY_HOME}/bin/sunwait"
fi
if [[ -n "${SUNWAIT_BIN}" ]]; then
  cp "${SUNWAIT_BIN}" /usr/local/bin/sunwait
  chmod +x /usr/local/bin/sunwait
  green "    sunwait installed to /usr/local/bin/."
elif ! command -v sunwait &>/dev/null; then
  # Try to compile sunwait if source exists.
  if [[ -f "${ALLSKY_HOME}/src/sunwait-src/sunwait.c" ]]; then
    cyan "    Compiling sunwait..."
    pushd "${ALLSKY_HOME}/src/sunwait-src" >/dev/null
    make -j"$(nproc)" 2>&1 | tail -3 || true
    popd >/dev/null
    if [[ -f "${ALLSKY_HOME}/src/sunwait-src/sunwait" ]]; then
      cp "${ALLSKY_HOME}/src/sunwait-src/sunwait" /usr/local/bin/sunwait
      chmod +x /usr/local/bin/sunwait
      green "    sunwait compiled and installed."
    fi
  fi
fi

# Always copy the options schema (it defines all settings for the web UI).
# This is safe to overwrite — it's a read-only schema, not user data.
if [[ -f "${ALLSKY_HOME}/config_repo/options.json.repo" ]]; then
  cp "${ALLSKY_HOME}/config_repo/options.json.repo" "${ALLSKY_HOME}/config/options.json"
fi

# Copy ALL .repo template files that allsky.sh needs at runtime.
for repo_file in RPi_cameraInfo.txt env.json autoexposure.json; do
  if [[ -f "${ALLSKY_HOME}/config_repo/${repo_file}.repo" ]]; then
    cp "${ALLSKY_HOME}/config_repo/${repo_file}.repo" "${ALLSKY_HOME}/config/${repo_file}"
  fi
done
# Copy ZWO camera info if present.
if [[ -f "${ALLSKY_HOME}/config_repo/ZWO_cameraInfo.txt.repo" ]]; then
  cp "${ALLSKY_HOME}/config_repo/ZWO_cameraInfo.txt.repo" "${ALLSKY_HOME}/config/ZWO_cameraInfo.txt"
fi

# Set up log rotation for allsky.
if [[ -f "${ALLSKY_HOME}/config_repo/allsky.logrotate.repo" ]]; then
  cp "${ALLSKY_HOME}/config_repo/allsky.logrotate.repo" /etc/logrotate.d/allsky 2>/dev/null || true
fi
if [[ -f "${ALLSKY_HOME}/config_repo/allsky.rsyslog.repo" ]]; then
  cp "${ALLSKY_HOME}/config_repo/allsky.rsyslog.repo" /etc/rsyslog.d/allsky.conf 2>/dev/null || true
  systemctl restart rsyslog 2>/dev/null || true
fi

green "    Config templates installed."

# Fix camera model name and ensure cameranumber is a string in ALL settings copies.
if command -v python3 &>/dev/null && [[ -f "${ALLSKY_HOME}/config/RPi_cameraInfo.txt" ]]; then
  python3 -c "
import json, sys, os
info_path = '${ALLSKY_HOME}/config/RPi_cameraInfo.txt'
# Fix both allsky home and web config copies.
paths = ['${ALLSKY_HOME}/config/settings.json', '${INSTALL_PREFIX}/config/settings.json']
for settings_path in paths:
    try:
        if not os.path.exists(settings_path):
            continue
        with open(settings_path) as f:
            settings = json.load(f)
        changed = False
        # Fix model name: sensor only -> full model from camera info.
        model = settings.get('cameramodel', '')
        if model and ' ' not in model:
            with open(info_path) as f:
                for line in f:
                    if line.startswith('camera\t'):
                        parts = line.split('\t')
                        if len(parts) >= 4 and parts[1].strip() == model:
                            settings['cameramodel'] = parts[3].strip()
                            changed = True
                            print(f'    Fixed cameramodel in {settings_path}: {model} -> {settings[\"cameramodel\"]}')
                            break
        # Ensure cameranumber is a string (capture binary expects string).
        cn = settings.get('cameranumber')
        if isinstance(cn, int):
            settings['cameranumber'] = str(cn)
            changed = True
        if changed:
            with open(settings_path, 'w') as out:
                json.dump(settings, out, indent=4)
    except Exception as e:
        print(f'    Warning: could not fix {settings_path}: {e}')
" 2>&1
fi

# Create initial settings.json if missing (first install).
if [[ ! -f "${ALLSKY_HOME}/config/settings.json" ]]; then
  echo '{"cameratype":"RPi","cameramodel":"","cameranumber":"0","filename":"image.jpg","debuglevel":"1","lastchanged":"1"}' \
    > "${ALLSKY_HOME}/config/settings.json"
  green "    Created initial settings."
fi
# Ensure lastchanged exists (required by allsky.sh to know setup was completed).
if command -v jq &>/dev/null; then
  if [[ -f "${ALLSKY_HOME}/config/settings.json" ]]; then
    HAS_LC="$(jq -r '.lastchanged // empty' "${ALLSKY_HOME}/config/settings.json" 2>/dev/null)"
    if [[ -z "${HAS_LC}" ]]; then
      jq '. + {"lastchanged": "1"}' "${ALLSKY_HOME}/config/settings.json" > "${ALLSKY_HOME}/config/settings.json.tmp" && \
        mv "${ALLSKY_HOME}/config/settings.json.tmp" "${ALLSKY_HOME}/config/settings.json"
      green "    Added lastchanged to settings.json."
    fi
  fi
fi
# Also sync from web config copy if it has more recent data.
if [[ -f "${INSTALL_PREFIX}/config/settings.json" ]]; then
  # Copy web config back to allsky home so camera daemon gets latest settings.
  cp "${INSTALL_PREFIX}/config/settings.json" "${ALLSKY_HOME}/config/settings.json" 2>/dev/null || true
fi
# Always refresh status.
echo '{"status":"Not configured"}' > "${ALLSKY_HOME}/config/status.json"

# Always update allsky.service to ensure correct ALLSKY_HOME path.
# A previous install may have written a stale path.
cat >/etc/systemd/system/allsky.service <<ASEOF
[Unit]
Description=Allsky Camera
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SUDO_USER:-pi}
Environment=ALLSKY_HOME=${ALLSKY_HOME}
ExecStart=${ALLSKY_HOME}/allsky.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
ASEOF
systemctl daemon-reload
systemctl enable allsky.service
green "    Updated allsky.service (ExecStart=${ALLSKY_HOME}/allsky.sh)."

# Set up Python venv for Allsky's own modules (flow-runner, etc.).
if [[ ! -d "${ALLSKY_HOME}/venv" ]]; then
  cyan "    Creating Allsky Python venv..."
  # --system-site-packages lets it use system numpy/opencv if available.
  python3 -m venv --system-site-packages "${ALLSKY_HOME}/venv"
  # Explicitly install setuptools first (missing by default on Python 3.12+).
  "${ALLSKY_HOME}/venv/bin/python3" -m ensurepip --upgrade 2>/dev/null || true
  "${ALLSKY_HOME}/venv/bin/pip" install --quiet --upgrade pip setuptools wheel 2>&1 | tail -1 || true
  # Install Allsky's Python requirements if they exist.
  for req in "${ALLSKY_HOME}/config_repo/requirements"*.txt; do
    if [[ -f "$req" ]]; then
      cyan "    Installing from $(basename "$req")..."
      "${ALLSKY_HOME}/venv/bin/pip" install --quiet -r "$req" 2>&1 | tail -3 || true
    fi
  done
  green "    Allsky Python venv created."
fi

# Set permissions.
REAL_USER="${SUDO_USER:-pi}"
REAL_GROUP="$(id -gn "${REAL_USER}" 2>/dev/null || echo "${REAL_USER}")"
chown -R "${REAL_USER}:${REAL_GROUP}" "${ALLSKY_HOME}"

# Web UI service user needs read access to config/ and write access to tmp/.
# We use world-readable (o+r) on config files because group membership alone
# is unreliable — the service user's login group may differ, and supplementary
# groups aren't always picked up by systemd without a reboot.
chmod 755 "${ALLSKY_HOME}" 2>/dev/null || true
chmod 775 "${ALLSKY_HOME}/tmp" 2>/dev/null || true

# Make config directory and all files world-readable.
chmod -R o+rX "${ALLSKY_HOME}/config" 2>/dev/null || true
# Explicitly ensure key files are readable.
chmod o+r "${ALLSKY_HOME}/config/settings.json" 2>/dev/null || true
chmod o+r "${ALLSKY_HOME}/config/options.json" 2>/dev/null || true
chmod o+r "${ALLSKY_HOME}/config/status.json" 2>/dev/null || true

# Also make images, html (keograms/startrails/videos) readable.
chmod -R o+rX "${ALLSKY_HOME}/images" 2>/dev/null || true
chmod -R o+rX "${ALLSKY_HOME}/html" 2>/dev/null || true

# Ensure parent dirs are traversable (e.g. /home/username).
PARENT_DIR="$(dirname "${ALLSKY_HOME}")"
chmod o+rx "${PARENT_DIR}" 2>/dev/null || true

green "    Allsky backend setup done."

# ── Step 3: Web UI service user ──────────────────────────────────

cyan "==> [3/6] Creating web UI service user"
if ! id -u "${SERVICE_USER}" &>/dev/null; then
  useradd --system --create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
  green "    Created ${SERVICE_USER}."
else
  green "    ${SERVICE_USER} already exists."
fi
# Add to user's group + video group (camera access) + systemd-journal (log reading).
usermod -a -G "${REAL_GROUP}" "${SERVICE_USER}" 2>/dev/null || true
usermod -a -G video "${SERVICE_USER}" 2>/dev/null || true
usermod -a -G systemd-journal "${SERVICE_USER}" 2>/dev/null || true
green "    ${SERVICE_USER} added to groups: ${REAL_GROUP}, video, systemd-journal."

# ── Step 4: Python backend ──────────────────────────────────────

cyan "==> [4/6] Installing Python web backend"
mkdir -p "${INSTALL_PREFIX}"
# Clean copy backend source (remove old first to avoid cp -r nesting).
rm -rf "${INSTALL_PREFIX}/backend/app" "${INSTALL_PREFIX}/backend/pyproject.toml"
cp -r "${SCRIPT_DIR}/backend/app" "${INSTALL_PREFIX}/backend/app"
cp "${SCRIPT_DIR}/backend/pyproject.toml" "${INSTALL_PREFIX}/backend/pyproject.toml"
find "${INSTALL_PREFIX}/backend" -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

VENV="${INSTALL_PREFIX}/backend/.venv"
if [[ ! -d "${VENV}" ]]; then
  python3 -m venv --system-site-packages "${VENV}"
fi
"${VENV}/bin/python3" -m ensurepip --upgrade 2>/dev/null || true
"${VENV}/bin/pip" install --quiet --upgrade pip wheel setuptools 2>&1 | tail -1 || true
cyan "    Installing Python packages (first run: 5-15 min on Pi 3B)..."
"${VENV}/bin/pip" install --quiet "${INSTALL_PREFIX}/backend" 2>&1 | tail -3 || {
  yellow "    Retrying verbose..."
  "${VENV}/bin/pip" install "${INSTALL_PREFIX}/backend" || {
    red "    pip install failed. Try: sudo apt install python3-dev libffi-dev"
    exit 1
  }
}
green "    Python backend installed."

# Copy config files to install prefix where the web service user can read them.
# This solves the persistent "Permission denied" on home dirs (Bookworm 700).
WEB_CONFIG="${INSTALL_PREFIX}/config"
mkdir -p "${WEB_CONFIG}"
for cfg in options.json settings.json status.json; do
  if [[ -f "${ALLSKY_HOME}/config/${cfg}" ]]; then
    cp "${ALLSKY_HOME}/config/${cfg}" "${WEB_CONFIG}/${cfg}"
  fi
done
chown -R "${REAL_USER}:${REAL_GROUP}" "${WEB_CONFIG}"
green "    Config files synced to ${WEB_CONFIG}."

# ── Step 5: React frontend ──────────────────────────────────────

cyan "==> [5/6] Building React frontend"
# Clean copy frontend source.
rm -rf "${INSTALL_PREFIX}/frontend/src" "${INSTALL_PREFIX}/frontend/index.html"
mkdir -p "${INSTALL_PREFIX}/frontend"
cp -r "${SCRIPT_DIR}/frontend/src" "${INSTALL_PREFIX}/frontend/src"
cp "${SCRIPT_DIR}/frontend/package.json" "${INSTALL_PREFIX}/frontend/package.json"
cp "${SCRIPT_DIR}/frontend/tsconfig.json" "${INSTALL_PREFIX}/frontend/tsconfig.json"
cp "${SCRIPT_DIR}/frontend/vite.config.ts" "${INSTALL_PREFIX}/frontend/vite.config.ts"
cp "${SCRIPT_DIR}/frontend/tailwind.config.js" "${INSTALL_PREFIX}/frontend/tailwind.config.js"
cp "${SCRIPT_DIR}/frontend/postcss.config.js" "${INSTALL_PREFIX}/frontend/postcss.config.js"
cp "${SCRIPT_DIR}/frontend/index.html" "${INSTALL_PREFIX}/frontend/index.html"
rm -rf "${INSTALL_PREFIX}/frontend/dist"
pushd "${INSTALL_PREFIX}/frontend" >/dev/null
npm install 2>&1 | tail -5
npm run build 2>&1 | tail -5
popd >/dev/null
if [[ ! -f "${INSTALL_PREFIX}/frontend/dist/index.html" ]]; then
  red "    Frontend build failed — dist/index.html not found."
  exit 1
fi
green "    Frontend built."

# Set ownership.
mkdir -p "${DATA_DIR}"
chown -R "${REAL_USER}:${REAL_GROUP}" "${DATA_DIR}" "${INSTALL_PREFIX}"

# ── Step 6: Services + config ───────────────────────────────────

cyan "==> [6/6] Configuring services"

# Environment file.
mkdir -p /etc/allsky-web
if [[ ! -f "${ENV_FILE}" ]]; then
  SECRET="$(head -c 32 /dev/urandom | base64 | tr -d '=+/' | head -c 44)"
  cat >"${ENV_FILE}" <<ENVEOF
ALLSKY_HOME=${ALLSKY_HOME}
ALLSKY_WEB_CONFIG=${INSTALL_PREFIX}/config
ALLSKY_WEB_DATA=${DATA_DIR}
ALLSKY_WEB_SECRET=${SECRET}
ALLSKY_WEB_HOST=0.0.0.0
ALLSKY_WEB_PORT=8000
ALLSKY_WEB_USER=
ALLSKY_WEB_PASS_HASH=
ENVEOF
  chmod 640 "${ENV_FILE}"
  chown root:"${REAL_GROUP}" "${ENV_FILE}"
else
  sed -i "s|^ALLSKY_HOME=.*|ALLSKY_HOME=${ALLSKY_HOME}|" "${ENV_FILE}"
  # Ensure ALLSKY_WEB_CONFIG is present (may be missing from older installs).
  if ! grep -q '^ALLSKY_WEB_CONFIG=' "${ENV_FILE}"; then
    sed -i "/^ALLSKY_HOME=/a ALLSKY_WEB_CONFIG=${INSTALL_PREFIX}/config" "${ENV_FILE}"
  else
    sed -i "s|^ALLSKY_WEB_CONFIG=.*|ALLSKY_WEB_CONFIG=${INSTALL_PREFIX}/config|" "${ENV_FILE}"
  fi
fi

# Web UI systemd service.
# Run as the REAL user (not allskyweb) to avoid all home directory permission
# issues. On Bookworm, home dirs are 700 and PAM resets chmod on login.
# Running as the file owner eliminates the problem entirely.
cat >/etc/systemd/system/allsky-web.service <<SVCEOF
[Unit]
Description=Allsky modern web interface
After=network-online.target allsky.service
Wants=network-online.target

[Service]
Type=simple
User=${REAL_USER}
Group=${REAL_GROUP}
EnvironmentFile=-${ENV_FILE}
WorkingDirectory=${INSTALL_PREFIX}/backend
ExecStart=${INSTALL_PREFIX}/backend/.venv/bin/uvicorn app.main:app \
    --host \${ALLSKY_WEB_HOST} --port \${ALLSKY_WEB_PORT} --proxy-headers \
    --forwarded-allow-ips='*'
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
SVCEOF

# Sudoers — allow web UI user to control services, enable camera, reboot, and shutdown.
cat >/etc/sudoers.d/allsky-web <<SUDOEOF
${REAL_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl start allsky.service
${REAL_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl stop allsky.service
${REAL_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart allsky.service
${REAL_USER} ALL=(root) NOPASSWD: /usr/bin/raspi-config nonint *
${REAL_USER} ALL=(root) NOPASSWD: /usr/sbin/reboot
${REAL_USER} ALL=(root) NOPASSWD: /usr/sbin/shutdown -h now
${REAL_USER} ALL=(root) NOPASSWD: /usr/bin/tee /boot/config.txt
${REAL_USER} ALL=(root) NOPASSWD: /usr/bin/tee /boot/firmware/config.txt
SUDOEOF
chmod 0440 /etc/sudoers.d/allsky-web
visudo -cf /etc/sudoers.d/allsky-web >/dev/null 2>&1 || true

systemctl daemon-reload
systemctl enable allsky-web.service

# No chmod needed — web service now runs as the same user who owns ALLSKY_HOME.

# Start the web UI.
systemctl restart allsky-web.service 2>/dev/null || systemctl start allsky-web.service || true

green "    Services configured."

# Verify the web service can read config files.
cyan "    Verifying config access..."
if sudo -u "${SERVICE_USER}" test -r "${INSTALL_PREFIX}/config/options.json" 2>/dev/null; then
  green "    Config files readable by ${SERVICE_USER}."
else
  yellow "    WARNING: ${SERVICE_USER} cannot read config files."
  yellow "    Attempting fix..."
  chown -R "${REAL_USER}:${REAL_GROUP}" "${INSTALL_PREFIX}/config"
  chmod -R 644 "${INSTALL_PREFIX}/config"/*.json 2>/dev/null || true
fi

# ── Done ─────────────────────────────────────────────────────────

sleep 2
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
PORT="$(grep -m1 '^ALLSKY_WEB_PORT=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2 || echo 8000)"

echo ""
green "================================================================="
green "  Installation complete!  Allsky Web v${VERSION}"
green "================================================================="
echo ""
if systemctl is-active --quiet allsky-web.service; then
  green "  Web UI is running  (v${VERSION})"
  cyan  "  Open: http://${IP:-<pi-ip>}:${PORT}"
else
  yellow "  Web UI may still be starting..."
  echo  "  Check: sudo journalctl -u allsky-web -n 30"
fi
echo ""
cyan  "  Everything is managed from the browser — no more terminal needed."
cyan  "  The setup wizard will guide you through camera configuration."
echo ""
