#!/usr/bin/env bash
# Verify a forward target ACTUALLY delivers -- publish a short test stream to
# the relay and watch the relay log for the forward to the destination.
#
# Usage: ./tools/verify-forward.sh <path> <url> <key> [seconds]
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="http://127.0.0.1:9997"
LOG="$DIR/mediamtx.log"

PATHNAME="${1:-land}"
URL="${2:-}"
KEY="${3:-}"
SECS="${4:-8}"

[ -z "$URL" ] && { echo "usage: $0 <path> <url> <key> [seconds]"; exit 1; }

enc() { python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }
case "$PATHNAME" in
  land) ENC="$(enc '~^land(/.*)?$')"; PUB="land/land" ;;
  vert) ENC="$(enc '~^vert(/.*)?$')"; PUB="vert/vert" ;;
  *) echo "unknown path '$PATHNAME'"; exit 1 ;;
esac

# Resolve the runtime path the way Aitum does it (server + "/" + key)
RUNTIME="$PATHNAME/$PATHNAME"

echo "==> setting forward: $URL"
curl -s -X PATCH "$API/v3/config/paths/patch/$ENC" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c '
import json,sys
print(json.dumps({"forward":[{"dest":sys.argv[1] + "#" + sys.argv[2]}]}))
' "$URL" "$KEY")" > /dev/null

MARK=$(wc -l < "$LOG")

echo "==> publishing ${SECS}s test stream to $PUB"
ffmpeg -hide_banner -loglevel error -re \
  -f lavfi -i "testsrc2=size=1920x1080:rate=30" \
  -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p \
  -g 60 -f flv "rtmp://127.0.0.1:1935/$RUNTIME" > "$DIR/test-out/verify-pub.log" 2>&1 &
PUB_PID=$!

sleep "$SECS"
kill "$PUB_PID" 2>/dev/null
sleep 2

echo
echo "==> relay log for this window:"
tail -n +$((MARK+1)) "$LOG" | grep -iE "forward|is publishing|ready|error|warn" | head -25
