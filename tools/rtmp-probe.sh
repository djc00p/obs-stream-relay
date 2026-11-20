#!/usr/bin/env bash
# Probe one platform's RTMP ingest and show the REAL rejection reason.
#
# ffmpeg collapses every server-side RTMP rejection into
# "Error opening output file ... Input/output error". The actual reason
# ("Invalid stream key", "already streaming", etc.) is in the RTMP
# connect/publish response, which ffmpeg does not print by default.
#
# This tries the variants that matter and reports what changed:
#   1. plain RTMP
#   2. RTMP over TLS (rtmps)
#   3. -rtmp_live live
#
# Usage: rtmp-probe.sh <name> <url> <key>

set -uo pipefail
NAME="$1"; URL="$2"; KEY="$3"
FULL="${URL}/${KEY}"

echo "--- $NAME ---"

run_probe() {
  local label="$1"; shift
  local log
  log="$(ffmpeg -hide_banner -loglevel info "$@" -f flv "$FULL" 2>&1)"
  if printf '%s' "$log" | grep -q "Lsize="; then
    printf '  %-22s ACCEPTED (muxed output)\n' "$label"
    return 0
  fi
  # Pull the interesting lines out of the failure.
  local reason
  reason="$(printf '%s' "$log" \
    | grep -iE "Server returned|Invalid|already|denied|rejected|Forbidden|Unauthorized|not found|503|404|403|401|Stream ID|exceeded|limit|geo|blacklist" \
    | grep -viE "^\[libx264" | head -2 | tr '\n' ' ')"
  if [ -z "$reason" ]; then
    reason="$(printf '%s' "$log" | grep -oiE "(IO error[^,]*|End of file|Connection refused|Connection reset|tls @ [^ ]*)" | head -1)"
  fi
  printf '  %-22s REJECTED  %s\n' "$label" "${reason:-<no detail>}"
  return 1
}

run_probe "rtmp" \
  -f lavfi -i "color=c=black:s=320x240:d=0.3:r=5" \
  -c:v libx264 -preset ultrafast -t 0.3

run_probe "rtmp -rtmp_live live" \
  -f lavfi -i "color=c=black:s=320x240:d=0.3:r=5" \
  -c:v libx264 -preset ultrafast -t 0.3 -rtmp_live live
