"""Probe which redirect URI is registered on the YouTube OAuth client.

Google answers `redirect_uri_mismatch` for an unregistered URI and
proceeds to the login screen for a registered one -- which makes the
auth endpoint an oracle for its own config.

Also used by youtube-token.py's detect_redirect_uri().
"""

import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request as _request
from env_writer import CONFIG

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

CANDIDATES = [
    "https://localhost",
    "http://localhost",
    "http://127.0.0.1",
    "https://127.0.0.1",
    "http://localhost:8080",
    "http://localhost:3000",
]


def probe_all():
    cfg = {}
    with open(CONFIG) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")

    cid = cfg.get("YT_CLIENT_ID", "")
    if not cid:
        print("error: YT_CLIENT_ID not set")
        return 1

    print("=== registered redirect URIs ===\n")
    print(f"  client_id: {cid[:30]}...\n")

    matches = []
    for uri in CANDIDATES:
        q = urllib.parse.urlencode({
            "client_id": cid,
            "redirect_uri": uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "state": "probe",
            "access_type": "offline",
            "prompt": "consent",
        })
        try:
            st, body = _request("GET", f"{AUTH_URL}?{q}")
        except Exception as e:
            print(f"  {uri:30} ERROR {type(e).__name__}")
            continue
        text = body if isinstance(body, str) else ""
        if "redirect_uri_mismatch" in text:
            verdict = "mismatch"
        elif "ServiceLogin" in text or "Sign in" in text or st == 200:
            verdict = "MATCH"
            matches.append(uri)
        else:
            verdict = f"other({st})"
        print(f"  {uri:30} {verdict}")

    print()
    if matches:
        print("Registered:")
        for m in matches:
            print(f"  >>> {m}")
        return 0
    print("No candidate matched -- add one in the Cloud console:")
    print("  APIs & Services -> Credentials -> OAuth client ->")
    print("  Authorized redirect URIs")
    return 1


if __name__ == "__main__":
    sys.exit(probe_all())
