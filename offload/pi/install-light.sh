#!/bin/bash
# Light client installer for a Raspberry Pi that only captures.
#
# Installs capture, day/night, auto-exposure, the thermal guard, and the
# sync agent. It does not install Node, the web UI, ffmpeg, ImageMagick, or
# Python OpenCV. The capture binary still links libopencv so it can read each
# JPEG back for the exposure mean.
#
# Usage: sudo ./install.sh --light
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
export ALLSKY_HOME="${SCRIPT_DIR}"

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo ./install.sh --light" >&2
  exit 1
fi

REAL_USER="${SUDO_USER:-pi}"
REAL_GROUP="$(id -gn "${REAL_USER}" 2>/dev/null || echo "${REAL_USER}")"

echo "==> Light client packages (no Node, ffmpeg, ImageMagick, or web UI)"
apt-get update -qq
apt-get install -y -qq \
  python3 rsync openssh-client jq \
  libcamera-apps \
  libopencv-dev libusb-1.0-0-dev pkg-config g++ make git \
  iw

if [[ ! -f "${ALLSKY_HOME}/src/sunwait-src/sunwait.c" ]]; then
  rm -rf "${ALLSKY_HOME}/src/sunwait-src"
  git clone --depth 1 https://github.com/risacher/sunwait.git \
    "${ALLSKY_HOME}/src/sunwait-src"
fi

HEADER_REPO="${ALLSKY_HOME}/src/include/allsky_common.h.repo"
HEADER_OUT="${ALLSKY_HOME}/src/include/allsky_common.h"
if [[ -f "${HEADER_REPO}" ]]; then
  sed \
    -e "s|XX_ALLSKY_HOME_XX|${ALLSKY_HOME}|g" \
    -e "s|XX_CONNECTED_CAMERAS_FILE_XX|${ALLSKY_HOME}/config/connected_cameras.txt|g" \
    -e "s|XX_RPI_CAMERA_INFO_FILE_XX|${ALLSKY_HOME}/config/RPi_cameraInfo.txt|g" \
    "${HEADER_REPO}" > "${HEADER_OUT}"
fi

echo "==> Building capture_RPi and sunwait"
make -C "${ALLSKY_HOME}/src" -j"$(nproc)" capture_RPi sunwait
mkdir -p "${ALLSKY_HOME}/bin"
cp "${ALLSKY_HOME}/src/capture_RPi" "${ALLSKY_HOME}/bin/"
if [[ -f "${ALLSKY_HOME}/src/sunwait" ]]; then
  cp "${ALLSKY_HOME}/src/sunwait" "${ALLSKY_HOME}/bin/sunwait"
  install -m 0755 "${ALLSKY_HOME}/src/sunwait" /usr/local/bin/sunwait
fi

if [[ -f "${ALLSKY_HOME}/scripts/convertJSON.py" ]]; then
  cat > "${ALLSKY_HOME}/scripts/convertJSON.php" <<'PHPSHIM'
#!/bin/bash
exec "$(dirname "$0")/convertJSON.py" "$@"
PHPSHIM
  chmod +x "${ALLSKY_HOME}/scripts/convertJSON.php" "${ALLSKY_HOME}/scripts/convertJSON.py"
fi

mkdir -p "${ALLSKY_HOME}"/{tmp,config,images,darks,bin,logs}
mkdir -p /var/lib/allsky/outbox
chown -R "${REAL_USER}:${REAL_GROUP}" /var/lib/allsky "${ALLSKY_HOME}"

if [[ ! -f "${ALLSKY_HOME}/config/settings.json" ]]; then
  cat > "${ALLSKY_HOME}/config/settings.json" <<'JSON'
{
  "cameratype": "RPi",
  "cameramodel": "imx462",
  "cameranumber": "0",
  "filename": "image.jpg",
  "quality": 90,
  "latitude": "",
  "longitude": "",
  "angle": -6,
  "lastchanged": "1",
  "nightmaxautoexposure": 10000,
  "nightexposure": 8000,
  "nightgain": 16,
  "nightmaxautogain": 29,
  "nightdelay": 500,
  "dayexposure": 300,
  "timelapsewidth": 1920,
  "timelapseheight": 0
}
JSON
fi

if [[ ! -f "${ALLSKY_HOME}/config/offload.json" ]]; then
  python3 - <<PY
import json
from pathlib import Path
src = Path("${ALLSKY_HOME}/config/offload.json.example")
dest = Path("${ALLSKY_HOME}/config/offload.json")
data = json.loads(src.read_text()) if src.is_file() else {}
data["mode"] = "capture-only"
data["jpeg_quality"] = 90
data.setdefault("outbox_dir", "/var/lib/allsky/outbox")
dest.write_text(json.dumps(data, indent=2) + "\n")
PY
fi
chown "${REAL_USER}:${REAL_GROUP}" "${ALLSKY_HOME}/config/offload.json" "${ALLSKY_HOME}/config/settings.json"

ALLSKY_TMP="${ALLSKY_HOME}/tmp"
mkdir -p "${ALLSKY_TMP}"
if [[ -f /etc/fstab ]] && ! grep -Eq "[[:space:]]${ALLSKY_TMP}[[:space:]]" /etc/fstab; then
  echo "tmpfs ${ALLSKY_TMP} tmpfs size=64M,noatime,lazytime,nodev,nosuid,mode=775,uid=${REAL_USER},gid=${REAL_GROUP} 0 0 # allsky-light-tmpfs" >> /etc/fstab
  mount "${ALLSKY_TMP}" 2>/dev/null || true
fi

cat >/etc/systemd/system/allsky.service <<EOF
[Unit]
Description=Allsky camera capture
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${REAL_USER}
Group=${REAL_GROUP}
Environment=ALLSKY_HOME=${ALLSKY_HOME}
ExecStart=${ALLSKY_HOME}/allsky.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/allsky-sync.service <<EOF
[Unit]
Description=Allsky offload sync
After=network-online.target allsky.service
Wants=network-online.target

[Service]
Type=simple
User=${REAL_USER}
Group=${REAL_GROUP}
Nice=19
IOSchedulingClass=idle
Environment=ALLSKY_HOME=${ALLSKY_HOME}
ExecStart=/usr/bin/python3 ${ALLSKY_HOME}/offload/sync_agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/allsky-thermal.service <<EOF
[Unit]
Description=Allsky thermal guard
After=allsky.service

[Service]
Type=simple
User=${REAL_USER}
Group=${REAL_GROUP}
Environment=ALLSKY_HOME=${ALLSKY_HOME}
ExecStart=/usr/bin/python3 ${ALLSKY_HOME}/offload/thermal_guard.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/allsky-wifi-powersave.service <<EOF
[Unit]
Description=Disable Wi-Fi power save for Allsky
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=${ALLSKY_HOME}/offload/pi/wifi-powersave.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/sudoers.d/allsky-light <<EOF
${REAL_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl start allsky.service
${REAL_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl stop allsky.service
${REAL_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart allsky.service
EOF
chmod 0440 /etc/sudoers.d/allsky-light

chmod 0755 "${ALLSKY_HOME}/offload/pi/wifi-powersave.sh" "${ALLSKY_HOME}/offload/pi/pi-heat.sh"
systemctl daemon-reload
systemctl enable allsky.service allsky-sync.service allsky-thermal.service allsky-wifi-powersave.service
systemctl start allsky-thermal.service allsky-wifi-powersave.service || true
systemctl start allsky-sync.service || true

echo
echo "Light client installed. The web UI is not running on this Pi."
echo "Edit ${ALLSKY_HOME}/config/offload.json (PC host, user, SSH key) before capture."
echo "Then: sudo systemctl start allsky"
echo "Optional heat tweaks: sudo ${ALLSKY_HOME}/offload/pi/pi-heat.sh"
echo "See README section 'Offload processing to a PC'."
