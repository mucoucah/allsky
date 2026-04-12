#!/bin/bash
# allsky-web installer (Raspberry Pi OS Bookworm 64-bit).
#
# Idempotent: safe to re-run after pulling new code. It does NOT touch the
# upstream Allsky installation in $ALLSKY_HOME.
set -euo pipefail

ALLSKY_HOME="${ALLSKY_HOME:-/home/${SUDO_USER:-pi}/allsky}"
INSTALL_PREFIX="${INSTALL_PREFIX:-/opt/allsky-web}"
DATA_DIR="${ALLSKY_WEB_DATA:-/var/lib/allsky-web}"
SERVICE_USER="${ALLSKY_WEB_USER_NAME:-allskyweb}"
ENV_FILE="/etc/allsky-web/env"

cyan() { printf "\033[36m%s\033[0m\n" "$*"; }
red()  { printf "\033[31m%s\033[0m\n" "$*"; }

if [[ $EUID -ne 0 ]]; then
  red "Please run with sudo: sudo ./install.sh"
  exit 1
fi

cyan "==> Checking upstream Allsky at ${ALLSKY_HOME}"
if [[ ! -d "${ALLSKY_HOME}" ]]; then
  red "Upstream Allsky not found at ${ALLSKY_HOME}. Install it first or set ALLSKY_HOME."
  exit 1
fi

cyan "==> Creating service user ${SERVICE_USER}"
if ! id -u "${SERVICE_USER}" &>/dev/null; then
  useradd --system --create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi
# Make sure the service user can read upstream Allsky's images and write masks.
# We add it to the group that owns ${ALLSKY_HOME} (typically the pi user's group).
ALLSKY_GROUP="$(stat -c '%G' "${ALLSKY_HOME}")"
usermod -a -G "${ALLSKY_GROUP}" "${SERVICE_USER}" || true

cyan "==> Installing OS packages"
apt-get update
apt-get install -y python3-venv python3-pip nodejs npm

cyan "==> Copying source to ${INSTALL_PREFIX}"
mkdir -p "${INSTALL_PREFIX}"
rsync -a --delete --exclude __pycache__ --exclude node_modules --exclude .venv \
  "$(dirname "$(realpath "$0")")/backend/"  "${INSTALL_PREFIX}/backend/"
rsync -a --delete --exclude node_modules \
  "$(dirname "$(realpath "$0")")/frontend/" "${INSTALL_PREFIX}/frontend/"

cyan "==> Creating Python virtualenv + installing deps"
python3 -m venv "${INSTALL_PREFIX}/backend/.venv"
"${INSTALL_PREFIX}/backend/.venv/bin/pip" install --upgrade pip wheel
"${INSTALL_PREFIX}/backend/.venv/bin/pip" install -e "${INSTALL_PREFIX}/backend"

cyan "==> Building React bundle"
pushd "${INSTALL_PREFIX}/frontend" >/dev/null
npm ci || npm install
npm run build
popd >/dev/null

cyan "==> Creating data dir ${DATA_DIR}"
mkdir -p "${DATA_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${DATA_DIR}" "${INSTALL_PREFIX}"

cyan "==> Writing /etc/allsky-web/env"
mkdir -p /etc/allsky-web
if [[ ! -f "${ENV_FILE}" ]]; then
  SECRET="$(head -c 32 /dev/urandom | base64)"
  cat >"${ENV_FILE}" <<EOF
ALLSKY_HOME=${ALLSKY_HOME}
ALLSKY_WEB_DATA=${DATA_DIR}
ALLSKY_WEB_SECRET=${SECRET}
# Set ALLSKY_WEB_USER and ALLSKY_WEB_PASS_HASH to require login.
# To generate a hash:
#   python3 -c "from passlib.hash import bcrypt; print(bcrypt.hash('YOUR-PASS'))"
ALLSKY_WEB_USER=
ALLSKY_WEB_PASS_HASH=
EOF
  chmod 640 "${ENV_FILE}"
fi

cyan "==> Installing systemd unit"
install -m 0644 deploy/allsky-web.service /etc/systemd/system/allsky-web.service
systemctl daemon-reload
systemctl enable allsky-web.service

cyan "==> Installing sudoers drop-in (gated systemctl on allsky.service)"
install -m 0440 deploy/sudoers.d/allsky-web /etc/sudoers.d/allsky-web
visudo -cf /etc/sudoers.d/allsky-web

cyan "==> Done. Start with: sudo systemctl start allsky-web"
cyan "    Then add the lighttpd vhost from deploy/lighttpd-allskyweb.conf"
cyan "    or browse directly to http://<pi-host>:8000 (LAN-only)."
