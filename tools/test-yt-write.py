"""Prove the YouTube token can actually WRITE.

We can't update a live broadcast (none are live). But we CAN prove the
token has youtube.force-ssl by asking the API what it can do.

Best proof: update one of the OLD broadcasts (from May) with its own
current title -- a no-op write. If the API accepts the PUT and returns
200, the token has write scope on liveBroadcasts.

That mutates a past broadcast's title to the SAME value, so nothing
visible changes.
"""
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

headers = {"Authorization": f"Bearer {cfg.get('YT_TOKEN','')}",
           "Content-Type": "application/json"}
key = cfg.get("YT_API_KEY", "")
if key:
    headers["X-Goog-Api-Key"] = key

# Pick the most recent broadcast.
q = urllib.parse.urlencode({"part": "snippet", "mine": "true"})
st, data = _request("GET", f"https://www.googleapis.com/youtube/v3/liveBroadcasts?{q}",
                    headers=headers)
if st != 200:
    print(f"list failed: HTTP {st} {json.dumps(data)[:300]}")
    sys.exit(1)

items = data.get("items") or []
if not items:
    print("no broadcasts at all")
    sys.exit(1)

b = items[0]
bid = b.get("id")
cur_title = b.get("snippet", {}).get("title", "")
cur_cat = b.get("snippet", {}).get("categoryId", "")

print("=== YouTube write test ===\n")
print(f"  target broadcast : {bid}")
print(f"  current title    : {cur_title!r}")
print(f"  current category : {cur_cat}")
print(f"  (writing the SAME values back -- no visible change)\n")

# A PUT REPLACES the resource, so we must send the whole snippet back,
# not just the title. Send every snippet field we got, with only the
# title/category possibly changed.
snippet = dict(b.get("snippet", {}))
snippet["title"] = cur_title
if cur_cat:
    snippet["categoryId"] = cur_cat
body = {"id": bid, "snippet": snippet}

q2 = urllib.parse.urlencode({"part": "snippet", "id": bid})
st2, data2 = _request("PUT", f"https://www.googleapis.com/youtube/v3/liveBroadcasts?{q2}",
                       headers=headers, body=body)

print(f"  PUT liveBroadcasts -> HTTP {st2}")
if st2 == 200:
    got = data2.get("snippet", {})
    print(f"  returned title    : {got.get('title')!r}")
    print(f"  returned category : {got.get('categoryId')}")
    print()
    print("  ✓ WRITE CONFIRMED -- the token has youtube.force-ssl")
    print("    and can update a broadcast title.")
    sys.exit(0)

err = data2.get("error", {}) if isinstance(data2, dict) else {}
print(f"  error: {err.get('message', str(data2)[:300])}")
if err.get("status") == "403":
    print()
    print("  403 -> the token lacks write scope, OR the broadcast is")
    print("  owned by a different channel, OR the broadcast is too old")
    print("  (YouTube only allows editing recent broadcasts).")
sys.exit(1)
