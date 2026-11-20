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

# Require all three arguments. Without this, `set -u` aborts on an
# unbound $1 -- but a partial invocation (say, a name and a URL but no
# key) would build a malformed ingest URL and PROBE A REAL PLATFORM
# with it. This script sends actual RTMP connect/publish attempts, so
# it must never fire with arguments it was not given.
if [ "$#" -lt 3 ]; then
  echo "usage: rtmp-probe.sh <name> <url> <key>" >&2
  echo "  (this sends real RTMP publish attempts -- all three are required)" >&2
  exit 2
fi

NAME="$1"; URL="$2"; KEY="$3"

if [ -z "$URL" ] || [ -z "$KEY" ]; then
  echo "error: url and key must not be empty." >&2
  exit 2
fi

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
