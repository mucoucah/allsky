# Parse `rpicam-still --list-cameras` / `rpicam-hello --list-cameras`.
#
# rpicam-apps 1.15 (Raspberry Pi OS Trixie) prints a header, then one camera
# per line, then indented mode lines. Older libcamera-apps omitted the header
# and the bit depth. Libcamera logs on stderr are mixed in when the caller
# redirects 2>&1. Only a line shaped like "0 : imx290 [1920x1080 ...]" is a camera.
#
# Output is the tab-separated record allsky.sh expects:
#   RPi <camera number> <sensor>

{
	line = $0
	sub(/\r$/, "", line)
	sub(/^[[:space:]]+/, "", line)
	if (line ~ /^[0-9]+[[:space:]]*:[[:space:]]*[^[:space:]]+/) {
		match(line, /^[0-9]+/)
		num = substr(line, RSTART, RLENGTH) + 0
		rest = substr(line, RSTART + RLENGTH)
		sub(/^[[:space:]]*:[[:space:]]*/, "", rest)
		split(rest, parts, /[[:space:]]+/)
		sensor = parts[1]
		# A mode resolution ("1920x1080") is not a sensor name.
		if (sensor != "" && sensor !~ /^[0-9]+x[0-9]+$/ && sensor !~ /^Modes:?$/) {
			printf("RPi\t%d\t%s\n", num, sensor)
		}
	}
}
