#!/usr/bin/env bash
# Build the preview page's static assets and hand the directory to launchd.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$DIR/test-out/preview"
PORT="${1:-8899}"
mkdir -p "$WORK"

curl -s "http://127.0.0.1:9997/v3/paths/list" -o "$WORK/paths-list.json"
python3 "$DIR/../tools/build-paths-json.py" "$WORK/paths-list.json" "$WORK/paths.json"
cp "$DIR/../tools/preview/index.html" "$WORK/index.html"
curl -s --max-time 15 "http://127.0.0.1:8888/land/land/hls.min.js" -o "$WORK/hls.min.js"

echo "preview assets ready in $WORK (port $PORT)"
