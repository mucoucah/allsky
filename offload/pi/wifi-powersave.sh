#!/bin/bash
# Turn off Wi-Fi power save on every wlan interface. A dropped association
# during an 8 second exposure is worse than the small extra power draw.
set -u
if ! command -v iw >/dev/null 2>&1; then
  echo "iw is not installed" >&2
  exit 0
fi
found=0
for dev in /sys/class/net/wlan*; do
  [[ -e ${dev} ]] || continue
  name="$(basename "${dev}")"
  iw dev "${name}" set power_save off && found=1 || true
  echo "power save off for ${name}"
done
if [[ ${found} -eq 0 ]]; then
  echo "no wlan interface yet"
fi
exit 0
