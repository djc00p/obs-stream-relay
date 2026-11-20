"""Is the Kick channel live?

Same reasoning as Twitch: a publish to an already-live channel is
rejected, and ffmpeg reports it as a generic I/O error.

Also checks whether the Kick stream key is still the current one.
Kick's key can be read via the API with the broadcaster token.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request as _request

BASE = "$RELAY_DIR"


def read(path):
    cfg = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def main():
    meta = read(f"{BASE}/stream-meta.env")
    keys = read(f"{BASE}/stream-keys.env")
    h = {"Authorization": f"Bearer {meta.get('KICK_TOKEN','')}"}
    slug = keys.get("KICK_CHANNEL_SLUG", meta.get("KICK_CHANNEL_SLUG", ""))

    print("=== Kick channel state ===\n")
    st, d = _request(
        "GET", f"https://api.kick.com/public/v1/channels?slug={slug}",
        headers=h)
    print(f"  GET /channels?slug={slug} -> HTTP {st}")
    if st != 200:
        print(f"  {json.dumps(d)[:300]}")
        return 1

    items = d.get("data") or []
    if not items:
        print("  no channel returned")
        return 1

    ch = items[0]
    ls = ch.get("livestream") or {}
    is_live = bool(ch.get("stream", {}).get("is_live"))
    print(f"  broadcaster_user_id : {ch.get('broadcaster_user_id')}")
    print(f"  stream.is_live      : {is_live}")
    print(f"  livestream present  : {bool(ls)}")
    if ls:
        print(f"  session_title       : {ls.get('session_title')!r}")
        print(f"  is_live             : {ls.get('is_live')}")
        print(f"  viewers             : {ls.get('viewer_count')}")
        print(f"  started             : {ls.get('start_time')}")
    print()

    if is_live:
        print("  *** CHANNEL IS LIVE ***")
        print("  Kick allows one broadcast per channel. A publish to a")
        print("  live channel is rejected. That is the 'tls IO error:")
        print("  End of file' symptom -- the server closes the")
        print("  connection instead of replying with an error.")
        return 2

    print("  channel is NOT live.")
    print()
    print("  Kick stream keys are single-use-ish and expire. If the")
    print("  channel is not live and the key is still rejected, the key")
    print("  is stale -- copy a fresh one from Kick's dashboard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
