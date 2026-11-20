#!/usr/bin/env bash
# Simulate Aitum's publish behavior: server + "/" + stream_key as the path.
# Publishes land/land and vert/vert, then runs check-wiring.sh to prove the
# matcher resolves the real runtime paths.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$DIR/test-out"

echo "=== publishing like Aitum does (path = server + key) ==="
ffmpeg -hide_banner -loglevel error -re -f lavfi -i "testsrc=size=1920x1080:rate=30" \
  -f lavfi -i "anullsrc=channel_layout=stereo:sample_rate=48000" \
  -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p \
  -g 60 -c:a aac -b:a 128k -f flv "rtmp://127.0.0.1:1935/land/land" \
  > "$DIR/test-out/sim-land.log" 2>&1 &
LAND_PID=$!

ffmpeg -hide_banner -loglevel error -re -f lavfi -i "testsrc=size=1080x1920:rate=30" \
  -f lavfi -i "anullsrc=channel_layout=stereo:sample_rate=48000" \
  -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p \
  -g 60 -c:a aac -b:a 128k -f flv "rtmp://127.0.0.1:1935/vert/vert" \
  > "$DIR/test-out/sim-vert.log" 2>&1 &
VERT_PID=$!

sleep 8
echo "  publishers up (land pid=$LAND_PID, vert pid=$VERT_PID)"
echo
bash "$DIR/check-wiring.sh"
echo
echo "=== stopping simulators ==="
kill "$LAND_PID" "$VERT_PID" 2>/dev/null
sleep 2
echo "done"
