"""Verify the YouTube API key works and resolves the channel.

Uses channels?forHandle= which needs only the API key (no OAuth).
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request as _request
from env_writer import CONFIG

API = "https://www.googleapis.com/youtube/v3"

cfg = {}
with open(CONFIG) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")

key = cfg.get("YT_API_KEY", "")
handle = cfg.get("YT_CHANNEL_HANDLE", "")
expected = cfg.get("YT_CHANNEL_ID", "")

if not key:
    print("error: YT_API_KEY not set")
    sys.exit(1)

print("=== YouTube API key verification ===\n")
print(f"  api_key  : {key[:8]}...{key[-4:]}")
print(f"  handle   : {handle}")
print(f"  expected : {expected}")
print()

import urllib.parse
q = urllib.parse.urlencode({"forHandle": handle.lstrip("@"), "key": key})
st, data = _request("GET", f"{API}/channels?{q}")

print(f"  HTTP {st}")
if st != 200:
    print(f"  {json.dumps(data)[:400]}")
    sys.exit(1)

items = data.get("items") or []
if not items:
    print("  no channel returned")
    print(f"  {json.dumps(data)[:400]}")
    sys.exit(1)

ch = items[0]
snip = ch.get("snippet", {})
print()
print(f"  title      : {snip.get('title')}")
print(f"  channel_id : {ch.get('id')}")
print(f"  customUrl  : {snip.get('customUrl')}")
print()

failures = []
if ch.get("id") != expected:
    print(f"  FAIL  channel id mismatch")
    print(f"        config  : {expected}")
    print(f"        from API: {ch.get('id')}")
    failures.append("channel id")
else:
    print("  PASS  channel id matches the config")

if handle.lstrip("@").lower() == (snip.get("customUrl") or "").lstrip("@").lower():
    print(f"  PASS  handle resolves to this channel")
else:
    print(f"  FAIL  handle {handle} resolved to {snip.get('customUrl')}")
    failures.append("handle")

print()
if failures:
    print(f"FAILED: {len(failures)}")
    sys.exit(1)
print("ALL CHECKS PASSED")
