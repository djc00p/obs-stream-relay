"""What does the Twitch token actually have, and is the channel live?

GET /helix/users with the token returns the scopes it was granted.
GET /helix/streams?user_id= shows whether the channel is live.

Twitch rejects a publish to a channel that is ALREADY broadcasting.
That is the single most common cause of "handshake accepted, publish
rejected" and it is invisible in ffmpeg's error.
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
    uid = meta.get("TWITCH_USER_ID", "")

    print("=== Twitch token ===\n")
    st, d = _request("GET", "https://api.twitch.tv/helix/users", headers=h)
    if st == 200 and d.get("data"):
        u = d["data"][0]
        print(f"  HTTP {st}")
        print(f"  user_id   : {u.get('id')}")
        print(f"  login     : {u.get('login')}")
        print(f"  scopes    : {u.get('scopes')}")
        print()
        scopes = (u.get("scopes") or [])
        needed = "channel:read:stream_key"
        print(f"  has {needed}: {needed in scopes}")
    else:
        print(f"  HTTP {st}  {json.dumps(d)[:200]}")
        print()
        print("  Token cannot even read /users -- it may be expired.")
        return 1

    print("\n=== is the channel live? ===\n")
    st2, d2 = _request("GET",
                       f"https://api.twitch.tv/helix/streams?user_id={uid}",
                       headers=h)
    if st2 != 200:
        print(f"  HTTP {st2}  {json.dumps(d2)[:200]}")
        return 1

    streams = d2.get("data") or []
    if streams:
        s = streams[0]
        print("  *** CHANNEL IS LIVE ***")
        print(f"    title    : {s.get('title')!r}")
        print(f"    game     : {s.get('game_name')!r}")
        print(f"    viewers  : {s.get('viewer_count')}")
        print(f"    started  : {s.get('started_at')}")
        print(f"    type     : {s.get('type')}")
        print()
        print("  Twitch allows ONE broadcast per channel. A publish to a")
        print("  live channel is rejected -- which is exactly the")
        print("  'handshake OK, publish rejected' symptom.")
        return 2

    print("  channel is NOT live.")
    print()
    print("  If the channel is not live and the key matches, then the")
    print("  key itself is stale (Twitch rotates it when you click")
    print("  'Get Stream Key').")
    return 0


if __name__ == "__main__":
    sys.exit(main())
