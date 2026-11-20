#!/usr/bin/env bash
# Print the correct HLS preview URL(s) for the relay, resolving the LIVE
# runtime path names (which may be "land/land" or just "land" depending on
# whether the Aitum output has a stream key set).
#
# The ?cookieCheck=1 query is required over plain http:// -- see below.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$DIR/test-out"
curl -s "http://127.0.0.1:9997/v3/paths/list" -o "$DIR/test-out/paths-now.json"

python3 - "$DIR" <<'PY'
import json
import sys

dir_ = sys.argv[1]
with open(f"{dir_}/test-out/paths-now.json") as f:
    items = json.load(f).get("items") or []


def dims(it):
    for t in (it.get("tracks2") or []):
        if not isinstance(t, dict):
            continue
        p = t.get("codecProps") or {}
        if p.get("width"):
            return f"{p.get('width')}x{p.get('height')}"
    return "-"


names = [it.get("name") for it in items if it.get("name")]
for base in ("land", "vert"):
    # exact match first, then prefix (land -> land/land)
    hit = next((n for n in names if n == base), None)
    if hit is None:
        hit = next((n for n in names if n.startswith(base + "/")), None)
    if hit is None:
        print(f"  {base:<6} (not publishing)")
        continue
    d = next((dims(it) for it in items if it.get("name") == hit), "-")
    print(f"  {base:<6} http://127.0.0.1:8888/{hit}/index.m3u8?cookieCheck=1   [{d}]")
PY

cat <<'EOF'

  NOTE: the ?cookieCheck=1 query is REQUIRED over http://.
  MediaMTX sets a "Secure; HttpOnly" cookie and browsers refuse to store a
  Secure cookie over plain http, so the bare URL redirects back to itself
  without the cookie and shows "no stream is available" even when live.
EOF
