"""Check the real YouTube OAuth client against Google.

Sends the actual client_id/client_secret with a dummy code. Google
validates the client FIRST, so:
  - 401 invalid_client  -> the client id/secret is WRONG
  - 400 invalid_grant   -> the client is VALID, only the code was bad

Either way we learn whether the credentials we saved are good.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request_form as _request_form
from env_writer import CONFIG

TOKEN_URL = "https://oauth2.googleapis.com/token"

cfg = {}
with open(CONFIG) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")

cid = cfg.get("YT_CLIENT_ID", "")
csec = cfg.get("YT_CLIENT_SECRET", "")

if not cid or not csec:
    print("error: YT_CLIENT_ID / YT_CLIENT_SECRET not set in", CONFIG)
    sys.exit(1)

print("=== YouTube OAuth client validation ===\n")
print(f"  client_id     : {cid}")
print(f"  client_secret : {csec[:10]}...{csec[-4:]} (len {len(csec)})")
print()

st, data = _request_form("POST", TOKEN_URL, {
    "client_id": cid,
    "client_secret": csec,
    "code": "dummy-code-that-was-never-issued",
    "grant_type": "authorization_code",
    "redirect_uri": "http://localhost",
})

print(f"  HTTP {st}")
if isinstance(data, dict):
    for k in ("error", "error_description", "error_uri"):
        if k in data:
            print(f"  {k}: {data[k]}")
else:
    print(f"  {str(data)[:300]}")
print()

if st == 401 and isinstance(data, dict) and data.get("error") == "invalid_client":
    print("VERDICT: client id/secret is WRONG.")
    print("  Google did not recognize these credentials.")
    sys.exit(1)

if st == 400 and isinstance(data, dict) and data.get("error") in (
        "invalid_grant", "invalid_request"):
    print("VERDICT: client id/secret is VALID.")
    print("  Google accepted the credentials and only rejected the dummy code,")
    print("  which is exactly what we want to see.")
    print()
    print("  Next: run ./youtube-token.sh and complete the browser flow.")
    sys.exit(0)

print("VERDICT: unexpected response.")
sys.exit(1)
