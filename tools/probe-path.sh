#!/usr/bin/env bash
# Publish a synthetic stream to a relay path and report what the relay does.
# Proves whether a path with NO forward targets still accepts the stream
# (it should: the relay holds it and sends it nowhere).
# Usage: ./tools/probe-path.sh land [WxH]
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
P="${1:-land}"
SIZE="${2:-1920x1080}"

echo "Publishing ${SIZE} to rtmp://127.0.0.1:1935/${P} ..."
ffmpeg -hide_banner -loglevel error -re \
  -f lavfi -i "testsrc2=size=${SIZE}:rate=30" \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
  -f flv "rtmp://127.0.0.1:1935/${P}" > /dev/null 2>&1 &
FPID=$!
sleep 6

echo
echo "=== path state ==="
curl -s http://127.0.0.1:9997/v3/paths/list | python3 "$DIR/../tools/dump-paths.py"

echo
echo "=== forward targets on ${P} ==="
curl -s "http://127.0.0.1:9997/v3/config/paths/get/${P}" | python3 "$DIR/../tools/forward-list.py"
CNT=$(curl -s "http://127.0.0.1:9997/v3/config/paths/get/${P}" | python3 "$DIR/../tools/forward-list.py" count)
echo "(count=${CNT})"

echo
echo "=== relay log tail ==="
tail -8 "$DIR/mediamtx.log"

kill "$FPID" 2>/dev/null
wait "$FPID" 2>/dev/null
echo
echo "(publisher stopped)"
