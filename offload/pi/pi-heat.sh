#!/bin/bash
# Optional heat reductions for a headless Pi light client.
# Nothing here is required for capture. Review each flag before using it.
# Raspberry Pi OS Lite (no desktop) is the right base image.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

GOVERNOR="ondemand"
DISABLE_BT=0
DISABLE_HDMI=0
DISABLE_LEDS=0

usage() {
  echo "Usage: sudo $0 [--governor ondemand|powersave] [--disable-bt] [--disable-hdmi] [--disable-leds]"
  echo "With no flags, sets the CPU governor to ondemand and prints the other options."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --governor) GOVERNOR="$2"; shift 2 ;;
    --disable-bt) DISABLE_BT=1; shift ;;
    --disable-hdmi) DISABLE_HDMI=1; shift ;;
    --disable-leds) DISABLE_LEDS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -d /sys/devices/system/cpu/cpu0/cpufreq ]]; then
  for gov in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo "${GOVERNOR}" > "${gov}" || true
  done
  echo "CPU governor: ${GOVERNOR}"
else
  echo "cpufreq sysfs not present; governor left unchanged"
fi

CONFIG=""
for candidate in /boot/firmware/config.txt /boot/config.txt; do
  if [[ -f ${candidate} ]]; then
    CONFIG="${candidate}"
    break
  fi
done

append_config() {
  local line="$1"
  [[ -n ${CONFIG} ]] || return 0
  if grep -qxF "${line}" "${CONFIG}"; then
    return 0
  fi
  echo "${line}" >> "${CONFIG}"
  echo "added to ${CONFIG}: ${line}"
}

if [[ ${DISABLE_BT} -eq 1 ]]; then
  append_config "dtoverlay=disable-bt"
  systemctl disable --now bluetooth.service 2>/dev/null || true
  rfkill block bluetooth 2>/dev/null || true
fi

if [[ ${DISABLE_HDMI} -eq 1 ]]; then
  if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd display_power 0 || true
  fi
  echo "HDMI power off requested. Unplug the display. This does not remove the desktop package."
fi

if [[ ${DISABLE_LEDS} -eq 1 ]]; then
  append_config "dtparam=act_led_trigger=none"
  append_config "dtparam=pwr_led_trigger=none"
fi

echo
echo "Desktop: use Raspberry Pi OS Lite. Do not install a graphical session."
echo "Reboot if config.txt changed."
