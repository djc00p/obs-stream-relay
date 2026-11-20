"""Resolve the Twitch numeric broadcaster id and save it."""
import sys, os, urllib.parse, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request as _request
from env_writer import set_values, CONFIG

cfg = {}
with open(CONFIG) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")

headers = {
    "Client-ID": cfg.get("TWITCH_CLIENT_ID", ""),
    "Authorization": f"Bearer {cfg.get('TWITCH_TOKEN','')}",
}
login = cfg.get("TWITCH_USER_ID", "")
q = urllib.parse.urlencode({"login": login}) if login else ""
st, data = _request("GET", f"https://api.twitch.tv/helix/users?{q}", headers=headers)
print(f"HTTP {st}")
if st != 200:
    print(json.dumps(data)[:300]); sys.exit(1)

items = data.get("data") or []
if not items:
    print("no user returned"); sys.exit(1)

u = items[0]
print(f"  login    : {u.get('login')}")
print(f"  display  : {u.get('display_name')}")
print(f"  user_id  : {u.get('id')}")

ok, msg = set_values(CONFIG, {
    "TWITCH_USER_ID": str(u.get("id")),
    "TWITCH_CHANNEL_LOGIN": u.get("login", ""),
})
print(f"  {msg}")
sys.exit(0 if ok else 1)
