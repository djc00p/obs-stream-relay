#!/usr/bin/env bash
# Publish a synthetic stream to the relay, dump the raw API state, stop.
# Usage: ./tools/inspect-live.sh [land|vert] [WxH]
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATH_NAME="${1:-vert}"
SIZE="${2:-1080x1920}"

ffmpeg -hide_banner -loglevel error -re \
  -f lavfi -i "testsrc2=size=${SIZE}:rate=30" \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
  -f flv "rtmp://127.0.0.1:1935/${PATH_NAME}" > /dev/null 2>&1 &
FPID=$!
sleep 5

echo "=== raw /v3/paths/list ==="
curl -s http://127.0.0.1:9997/v3/paths/list | python3 "$DIR/../tools/raw-paths.py"

echo
echo "=== raw /v3/paths/get/${PATH_NAME} ==="
curl -s "http://127.0.0.1:9997/v3/paths/get/${PATH_NAME}" | python3 "$DIR/../tools/raw-paths.py"

kill "$FPID" 2>/dev/null
wait "$FPID" 2>/dev/null
echo
echo "(publisher stopped)"
