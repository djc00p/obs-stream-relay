#!/usr/bin/env bash
# Serve a local preview page for the relay's two streams.
#
# WHY THIS EXISTS:
#   1. Safari (and most browsers) will not PLAY a raw .m3u8 URL -- it offers to
#      download it as a file.
#   2. MediaMTX's HLS endpoints are protected by a cookie check that sets a
#      "Secure" cookie, which browsers refuse to store over plain http://.
#      So the bare playlist URL errors out even when the stream is live.
#
#   This page solves both: hls.js in a <video> tag, with ?cookieCheck=1
#   appended to every playlist request.
#
# Usage:  ./tools/preview-server.sh [port]     (default 8899)
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8899}"
WORK="$DIR/test-out/preview"
mkdir -p "$WORK"

echo "==> resolving live relay paths..."
curl -s "http://127.0.0.1:9997/v3/paths/list" -o "$WORK/paths-list.json"

python3 "$DIR/../tools/build-paths-json.py" "$WORK/paths-list.json" "$WORK/paths.json"
cp "$DIR/../tools/preview/index.html" "$WORK/index.html"

# MediaMTX ships hls.js; grab it from the running relay.
curl -s --max-time 15 "http://127.0.0.1:8888/land/land/hls.min.js" -o "$WORK/hls.min.js"
if [ ! -s "$WORK/hls.min.js" ]; then
  echo "    ! could not fetch hls.min.js — is the relay running?" >&2
else
  echo "    hls.js: $(wc -c < "$WORK/hls.min.js" | tr -d ' ') bytes"
fi

echo "    landscape : $(python3 -c 'import json;print(json.load(open("'"$WORK"'/paths.json"))["land"] or "<none>")')"
echo "    portrait  : $(python3 -c 'import json;print(json.load(open("'"$WORK"'/paths.json"))["vert"] or "<none>")')"
echo
echo "==> open http://127.0.0.1:$PORT/   (Ctrl-C to stop)"

cd "$WORK" && python3 -m http.server "$PORT" --bind 127.0.0.1
