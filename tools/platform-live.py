"""Report whether a channel is currently broadcasting.

Prints exactly one word on stdout:
    live      -- the channel is broadcasting right now
    offline   -- the channel is not broadcasting
    unknown   -- the check could not run (no token, network error, ...)

dry-run.sh calls this to tell "the channel is already live, so a
second publish is rejected" apart from "the key is wrong". Both look
identical in ffmpeg's generic error output.

Uses proxy_http rather than curl because the OpenClaw sandbox's egress
proxy blocks curl (http=000) while proxy_http falls back to a direct
connection.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request as _request

BASE = "$RELAY_DIR"


def read(path):
    cfg = {}
    if not os.path.exists(path):
        return cfg
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def check_twitch(meta):
    cid = meta.get("TWITCH_CLIENT_ID", "")
    tok = meta.get("TWITCH_TOKEN", "")
    uid = meta.get("TWITCH_USER_ID", "")
    if not (cid and tok and uid):
        return "unknown"
    h = {"Client-Id": cid, "Authorization": f"Bearer {tok}"}
    try:
        st, d = _request("GET",
                         f"https://api.twitch.tv/helix/streams?user_id={uid}",
                         headers=h)
    except Exception:
        return "unknown"
    if st != 200 or not isinstance(d, dict):
        return "unknown"
    return "live" if (d.get("data") or []) else "offline"


def check_kick(meta, keys):
    tok = meta.get("KICK_TOKEN", "")
    slug = keys.get("KICK_CHANNEL_SLUG", meta.get("KICK_CHANNEL_SLUG", ""))
    if not (tok and slug):
        return "unknown"
    h = {"Authorization": f"Bearer {tok}"}
    try:
        st, d = _request(
            "GET",
            f"https://api.kick.com/public/v1/channels?slug={slug}",
            headers=h)
    except Exception:
        return "unknown"
    if st != 200 or not isinstance(d, dict):
        return "unknown"
    items = d.get("data") or []
    if not items:
        return "offline"
    ch = items[0]
    if (ch.get("stream") or {}).get("is_live"):
        return "live"
    return "offline"


def main():
    platform = sys.argv[1] if len(sys.argv) > 1 else ""
    meta = read(f"{BASE}/stream-meta.env")
    keys = read(f"{BASE}/stream-keys.env")

    if platform == "twitch":
        result = check_twitch(meta)
    elif platform == "kick":
        result = check_kick(meta, keys)
    else:
        result = "unknown"

    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
