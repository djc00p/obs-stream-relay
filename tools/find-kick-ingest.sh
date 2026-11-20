#!/usr/bin/env bash
# =============================================================================
# find-kick-ingest.sh -- discover the working Kick RTMPS ingest URL
#
# Kick does not publish a static ingest URL the way Twitch does. Their Studio
# app fetches it at runtime from an authenticated API
# (rtmp_publish_path), so it cannot be looked up in a doc page.
#
# Instead of guessing, we PROBE candidate (host, path) combinations with a
# real RTMPS handshake using the user's actual stream key and report which
# one the platform ACCEPTS.
#
# A probe counts as ACCEPTED only when ffmpeg completes the handshake and
# muxes output (see dry-run.sh for the signal semantics).
#
# Usage:  ./tools/find-kick-ingest.sh [stream_key]
# =============================================================================

set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEYS_FILE="$DIR/../stream-keys.env"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; DIM=$'\033[2m'; NC=$'\033[0m'

KEY="${1:-}"
if [ -z "$KEY" ] && [ -f "$KEYS_FILE" ]; then
  # shellcheck disable=SC1090
  . "$KEYS_FILE"
  KEY="${KICK_KEY:-}"
fi

if [ -z "$KEY" ]; then
  echo "${RED}error:${NC} no KICK_KEY found (set it in stream-keys.env or pass it as an argument)"
  exit 1
fi

echo "${BOLD}=== Probing Kick ingest endpoints ===${NC}"
echo "${DIM}Each probe opens a real RTMPS handshake with your key.${NC}"
echo "${DIM}A successful probe means Kick ACCEPTED the credential on that URL.${NC}"
echo

CANDIDATES=(
  "rtmps://live.kick.com:443/live"
  "rtmps://live.kick.com:443/app"
  "rtmps://live.kick.com:443/kick"
  "rtmps://live.kick.com:443/rtmp"
  "rtmps://ingest.kick.com:443/live"
  "rtmps://ingest.kick.com:443/app"
  "rtmps://live.kick.com/live"
  "rtmps://live.kick.com/app"
  "rtmps://rtmp-api.kick.com:443/live"
  "rtmps://rtmp-api.kick.com:443/app"
  "rtmps://rtmp-api.kick.com:443/kick"
  "rtmps://api.kick.com:443/live"
  "rtmps://api.kick.com:443/app"
  "rtmps://edge.live.kick.com:443/live"
  "rtmps://edge.live.kick.com:443/app"
  "rtmps://ingest-global.live.kick.com:443/live"
  "rtmps://ingest-global.live.kick.com:443/app"
  "rtmp://live.kick.com:1935/live"
  "rtmp://live.kick.com:1935/app"
  "rtmp://ingest.kick.com:1935/live"
  "rtmp://ingest.kick.com:1935/app"
)

FOUND=""
for url in "${CANDIDATES[@]}"; do
  host="$(printf '%s' "$url" | sed -E 's#^[a-z]+://##; s#/.*$##; s#:[0-9]+$##')"
  port="$(printf '%s' "$url" | sed -En 's#.*:([0-9]+)/.*#\1#p')"
  [ -z "$port" ] && port=1935

  if ! nc -z -G 4 "$host" "$port" 2>/dev/null; then
    printf "  ${DIM}%-46s no route${NC}\n" "$url"
    continue
  fi

  log="$(ffmpeg -hide_banner -loglevel info \
          -f lavfi -i "color=c=black:s=320x240:d=0.2:r=5" \
          -c:v libx264 -preset ultrafast -t 0.2 \
          -f flv "$url/$KEY" 2>&1)"

  if printf '%s' "$log" | grep -q "Lsize="; then
    printf "  ${GREEN}✓ %-46s ACCEPTED${NC}\n" "$url"
    FOUND="$url"
    break
  elif printf '%s' "$log" | grep -q "Error opening output"; then
    printf "  ${YELLOW}%-46s reachable, rejected${NC}\n" "$url"
  else
    printf "  ${YELLOW}%-46s reachable, inconclusive${NC}\n" "$url"
  fi
done

echo
if [ -n "$FOUND" ]; then
  echo "${GREEN}${BOLD}  WORKING KICK INGEST URL: $FOUND${NC}"
  echo
  echo "  Update the relay with:"
  echo "    cd ~/Streaming-Relay"
  echo "    ./relay.sh add-forward land \"$FOUND\" \"\$KICK_KEY\""
  exit 0
else
  echo "${RED}${BOLD}  No candidate URL was accepted.${NC}"
  echo
  echo "  Most likely causes:"
  echo "   - the stream key is stale (Kick regenerates it; copy a fresh one)"
  echo "   - you are already broadcasting on Kick (only one RTMP at a time)"
  echo "   - Kick requires MFA/2FA to be confirmed for new stream sessions"
  echo
  echo "  Get a fresh key + the server URL from:"
  echo "    https://dashboard.kick.com/settings/broadcasting"
  echo "    (the 'Server URL' field next to your stream key)"
  exit 1
fi
