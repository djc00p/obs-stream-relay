"""Resolve a YouTube handle (@name) to its UC... channel id."""
import sys
sys.path.insert(0, "$RELAY_DIR/tools")
from proxy_http import request

HANDLE = sys.argv[1] if len(sys.argv) > 1 else "@YOUR_HANDLE"

# The channels/forHandle endpoint requires an API key. We don't have one
# yet, so try the public page scrape first.
url = f"https://www.youtube.com/{HANDLE}"
st, body = request("GET", url, timeout=20)
if st != 200:
    print(f"page HTTP {st}")
    sys.exit(1)

import re
print(f"page fetched: {len(body)} bytes")

m = re.search(r'"channelId":"(UC[^"]+)"', body)
if m:
    print(f"CHANNEL_ID={m.group(1)}")
    sys.exit(0)

m = re.search(r'"externalId":"(UC[^"]+)"', body)
if m:
    print(f"CHANNEL_ID={m.group(1)}")
    sys.exit(0)

print("no channelId found in page")
sys.exit(1)
