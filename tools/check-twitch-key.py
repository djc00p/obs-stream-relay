"""Validate the Twitch stream key via the Twitch API.

GET /helix/streams/key returns the key for the token's user. If our
stored TWITCH_KEY does not match what Twitch has, the key is STALE --
Twitch regenerates it when you click "Get Stream Key" in the dashboard,
and the old one stops working.

Also checks whether the channel is already live (Twitch rejects a
second publish on a channel that is already broadcasting).

Credentials come from stream-meta.env (TWITCH_CLIENT_ID /
TWITCH_TOKEN); the stream key comes from stream-keys.env.
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

    h = {"Client-Id": meta.get("TWITCH_CLIENT_ID", ""),
         "Authorization": f"Bearer {meta.get('TWITCH_TOKEN','')}"}

    stored = keys.get("TWITCH_KEY", "")
    print("=== Twitch stream key validation ===\n")
    print(f"  stored key : {stored[:14]}...{stored[-4:]} (len {len(stored)})")
    print()

    uid = meta.get("TWITCH_USER_ID", "")
    st, d = _request(
        "GET",
        f"https://api.twitch.tv/helix/streams/key?broadcaster_id={uid}",
        headers=h)
    print(f"  GET /helix/streams/key -> HTTP {st}")
    if st != 200:
        print(f"  {json.dumps(d)[:300]}")
        return 1

    items = d.get("data") or []
    if not items:
        print("  no key returned")
        return 1

    live_key = items[0].get("stream_key", "")
    print(f"  twitch key : {live_key[:14]}...{live_key[-4:]} (len {len(live_key)})")
    print(f"  MATCHES stored key: {live_key == stored}")
    print()

    uid = meta.get("TWITCH_USER_ID", "")
    st2, d2 = _request("GET",
                       f"https://api.twitch.tv/helix/streams?user_id={uid}",
                       headers=h)
    streams = d2.get("data") or []
    if streams:
        s = streams[0]
        print("  CHANNEL IS LIVE:")
        print(f"    title    : {s.get('title')!r}")
        print(f"    game     : {s.get('game_name')!r}")
        print(f"    viewers  : {s.get('viewer_count')}")
        print(f"    started  : {s.get('started_at')}")
        print()
        print("  Twitch rejects a publish to a channel that is already")
        print("  broadcasting. That is the likely cause of the rejection.")
    else:
        print("  channel is NOT currently live")

    print()
    if live_key != stored:
        print("  ACTION: the stored key is STALE. Copy the current key from")
        print("  the Twitch dashboard (Get Stream Key) into stream-keys.env.")
        return 1
    print("  stored key matches Twitch's current key")
    return 0


if __name__ == "__main__":
    sys.exit(main())
