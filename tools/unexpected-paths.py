"""List relay paths that are NOT the expected land/vert pair.

Why
---
The relay is meant to carry exactly two publishers:

    land/land   landscape   1920x1080
    vert/vert   portrait    1080x1920

But OBS plugins can publish to the relay on their own without being an Aitum
output. We found the "vertical-canvas" plugin running its own "restream alt
output" at rtmp://127.0.0.1:1935/vertical, which lands on the runtime path
"vertical/land". That path has no forward targets, so the plugin's stream
goes nowhere -- but it is still a live publisher burning encoder headroom and
a duplicate copy of the portrait feed on the wire.

This tool lists every live path that is not land*/vert* so check-wiring.sh
can flag it.

Usage:
    ./tools/unexpected-paths.py [--with-dims]
    curl -s http://127.0.0.1:9997/v3/paths/list | python3 tools/unexpected-paths.py
"""

import json
import os
import sys
import urllib.request

API = "http://127.0.0.1:9997/v3/paths/list"

# Path prefixes owned by the two intentional publishers.
EXPECTED_PREFIXES = ("land", "vert")

# Runtime paths we know about and why they're OK to see.
KNOWN_OK = {
    # MediaMTX's own internal HLS/reader artifacts never appear as paths, but
    # "all_others" is the catch-all config entry, not a runtime path.
    "all_others",
}


def dims(it):
    for t in (it.get("tracks2") or []):
        if not isinstance(t, dict):
            continue
        props = t.get("codecProps") or {}
        if props.get("width"):
            return f"{props.get('width')}x{props.get('height')}"
    return ""


def main():
    with_dims = True

    # If stdin is a TTY (or empty) fetch the data ourselves. This keeps the
    # tool runnable as a plain script, which the exec preflight requires.
    raw = ""
    if not sys.stdin.isatty():
        raw = sys.stdin.read()
    if not raw.strip():
        try:
            with urllib.request.urlopen(API, timeout=5) as r:
                raw = r.read().decode()
        except Exception as e:
            print(f"error: could not reach the relay API: {e}", file=sys.stderr)
            sys.exit(2)

    try:
        d = json.loads(raw)
    except Exception as e:
        print(f"error: could not parse API response: {e}", file=sys.stderr)
        sys.exit(2)

    items = d.get("items") or []

    unexpected = []
    for it in items:
        name = it.get("name") or ""
        if name in KNOWN_OK:
            continue
        top = name.split("/", 1)[0]
        if top in EXPECTED_PREFIXES:
            continue
        unexpected.append(it)

    if not unexpected:
        sys.exit(0)

    for it in unexpected:
        name = it.get("name")
        if with_dims:
            got = dims(it)
            print(f"{name}\t{got or 'no-video'}")
        else:
            print(name)


if __name__ == "__main__":
    main()
