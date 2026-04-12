#!/bin/bash
# allsky-web uninstaller. Removes everything installed by install.sh.
# Does NOT touch the upstream Allsky installation.
set -euo pipefail

SERVICE_USER="${ALLSKY_WEB_USER_NAME:-allskyweb}"
INSTALL_PREFIX="${INSTALL_PREFIX:-/opt/allsky-web}"
DATA_DIR="${ALLSKY_WEB_DATA:-/var/lib/allsky-web}"

red()   { printf "\033[31m%s\033[0m\n" "$*"; }
cyan()  { printf "\033[36m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }

if [[ $EUID -ne 0 ]]; then
  red "Please run with sudo: sudo ./uninstall.sh"
  exit 1
fi

echo ""
red "This will remove allsky-web and all its data."
read -rp "Continue? [y/N] " confirm
if [[ "${confirm,,}" != "y" ]]; then
  echo "Aborted."
  exit 0
fi

cyan "==> Stopping and disabling service"
systemctl stop allsky-web.service 2>/dev/null || true
systemctl disable allsky-web.service 2>/dev/null || true
rm -f /etc/systemd/system/allsky-web.service
systemctl daemon-reload

cyan "==> Removing sudoers drop-in"
rm -f /etc/sudoers.d/allsky-web

cyan "==> Removing install directory ${INSTALL_PREFIX}"
rm -rf "${INSTALL_PREFIX}"

cyan "==> Removing data directory ${DATA_DIR}"
rm -rf "${DATA_DIR}"

cyan "==> Removing env file"
rm -rf /etc/allsky-web

cyan "==> Removing service user ${SERVICE_USER}"
if id -u "${SERVICE_USER}" &>/dev/null; then
  userdel -r "${SERVICE_USER}" 2>/dev/null || userdel "${SERVICE_USER}" 2>/dev/null || true
fi

echo ""
green "allsky-web has been removed."
green "Your upstream Allsky installation was NOT touched."
