"""List the broadcasts on the channel so we can see which one is live."""
import sys, os, urllib.parse, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request as _request
from env_writer import CONFIG

cfg = {}
with open(CONFIG) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")

headers = {"Authorization": f"Bearer {cfg.get('YT_TOKEN','')}"}
key = cfg.get("YT_API_KEY", "")
if key:
    headers["X-Goog-Api-Key"] = key

q = urllib.parse.urlencode({"part": "snippet,contentDetails,status", "mine": "true"})
st, data = _request("GET", f"https://www.googleapis.com/youtube/v3/liveBroadcasts?{q}",
                    headers=headers)
print(f"HTTP {st}\n")
if st != 200:
    print(json.dumps(data)[:500])
    sys.exit(1)

items = data.get("items") or []
print(f"{len(items)} broadcast(s):\n")
for b in items:
    s = b.get("snippet", {})
    print(f"  id       : {b.get('id')}")
    print(f"  title    : {s.get('title')!r}")
    print(f"  category : {s.get('categoryId')}")
    print(f"  start    : {s.get('actualStartTime')}")
    print(f"  end      : {s.get('actualEndTime')}")
    cd = b.get("contentDetails", {})
    print(f"  status   : {b.get('status',{}).get('broadcastStatus')}")
    print()
