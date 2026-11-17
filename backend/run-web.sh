#!/bin/bash
# Launch the web UI. Trust X-Forwarded-* only when a proxy address is configured.
# A value of '*' is ignored so a direct LAN install does not accept spoofed client IPs.
set -euo pipefail

cd "$(dirname "$0")"
args=(--host "${ALLSKY_WEB_HOST:-0.0.0.0}" --port "${ALLSKY_WEB_PORT:-8000}")
allow="${ALLSKY_WEB_FORWARDED_ALLOW_IPS:-}"
if [[ -n "$allow" && "$allow" != "*" ]]; then
	args+=(--proxy-headers --forwarded-allow-ips="$allow")
fi
exec "$(dirname "$0")/.venv/bin/uvicorn" app.main:app "${args[@]}"
