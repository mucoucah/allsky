#!/bin/bash
# Append one vetted camera line to the Raspberry Pi boot config.
# The web UI is allowed to run only the subcommands listed in sudoers.
# Anything else is refused. This replaces a blanket "tee /boot/config.txt".
set -euo pipefail

cmd="${1:-}"
sensor="${2:-}"

cfg=""
for p in /boot/firmware/config.txt /boot/config.txt; do
	if [[ -f "$p" ]]; then
		cfg="$p"
		break
	fi
done
if [[ -z "$cfg" ]]; then
	echo "boot config not found" >&2
	exit 1
fi

append_once() {
	local line="$1"
	if grep -qxF "$line" "$cfg"; then
		echo "already present: $line"
		exit 0
	fi
	printf '\n%s\n' "$line" >>"$cfg"
	echo "appended to $cfg: $line"
}

case "$cmd" in
	enable-camera-autodetect)
		append_once "camera_auto_detect=1"
		;;
	add-overlay)
		case "$sensor" in
			imx290 | imx462) line="dtoverlay=imx290,clock-frequency=74250000" ;;
			imx477) line="dtoverlay=imx477" ;;
			imx708) line="dtoverlay=imx708" ;;
			imx219) line="dtoverlay=imx219" ;;
			ov5647) line="dtoverlay=ov5647" ;;
			imx519) line="dtoverlay=imx519" ;;
			arducam_64mp) line="dtoverlay=arducam-64mp" ;;
			*)
				echo "refusing overlay for '${sensor}'" >&2
				exit 2
				;;
		esac
		append_once "$line"
		;;
	*)
		echo "usage: allsky-boot-config enable-camera-autodetect | add-overlay SENSOR" >&2
		exit 2
		;;
esac
