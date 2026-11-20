#!/usr/bin/env bash
# Refresh the preview page's paths.json + hls.js from the live relay.
# Run by launchd every 15s so the preview page always reflects the relay.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$DIR/../tools/preview"
STATE="$DIR/test-out/preview"
mkdir -p "$STATE" "$WORK"

curl -s --max-time 5 "http://127.0.0.1:9997/v3/paths/list" -o "$STATE/paths-list.json" || exit 0
python3 "$DIR/../tools/build-paths-json.py" "$STATE/paths-list.json" "$STATE/paths.json" || exit 0

# The server serves index.html + paths.json + hls.min.js from its own dir.
cp "$DIR/../tools/preview/index.html" "$WORK/index.html"
cp "$STATE/paths.json" "$WORK/paths.json"

# hls.js only changes on relay upgrades -- refresh it occasionally.
if [ ! -s "$WORK/hls.min.js" ]; then
  curl -s --max-time 15 "http://127.0.0.1:8888/land/land/hls.min.js" -o "$WORK/hls.min.js" || true
fi
