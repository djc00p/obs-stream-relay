#!/usr/bin/env python3
"""YouTube OAuth token helper.

Gets an access token for the YouTube Data API and WRITES it into
stream-meta.env as YT_TOKEN. Nothing to copy-paste.

Follows the same pattern as tools/kick-token.py:
  - reads client id / secret from the config when flags are omitted
  - opens the browser (or prints the URL)
  - you approve, the redirect lands on http://localhost/?code=...
  - paste that URL back
  - the token is exchanged and the file is written

Scope: youtube.force-ssl is what stream-meta.sh needs to UPDATE a
broadcast title/category. youtube.upload is not needed for that.

Usage:
    ./youtube-token.sh
    ./youtube-token.sh --no-open
"""

import argparse
import hashlib
import json
import os
import random
import string
import subprocess
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request as _request
from proxy_http import request_form as _request_form
from env_writer import set_values, CONFIG

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
# The redirect URI MUST exactly match one of the "Authorized redirect
# URIs" on the OAuth client. the client registers:
#     https://localhost
# NOT http://localhost -- using the wrong scheme gives
# redirect_uri_mismatch. The helper detects the registered value at
# runtime (see detect_redirect_uri) instead of hardcoding one.
REDIRECT_CANDIDATES = [
    "https://localhost",
    "http://localhost",
    "http://127.0.0.1",
    "https://127.0.0.1",
]
SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def detect_redirect_uri(client_id):
    """Find which redirect URI is registered on the OAuth client.

    Google answers redirect_uri_mismatch for a URI that isn't
    registered, and proceeds to the login screen for one that is. That
    makes the auth endpoint an oracle for its own config.

    Returns the matching URI, or None.
    """
    for uri in REDIRECT_CANDIDATES:
        q = {
            "client_id": client_id,
            "redirect_uri": uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "state": "probe",
            "access_type": "offline",
            "prompt": "consent",
        }
        try:
            st, body = _request("GET", f"{AUTH_URL}?{urllib.parse.urlencode(q)}")
        except Exception:
            continue
        text = body if isinstance(body, str) else ""
        if "redirect_uri_mismatch" in text:
            continue
        if "ServiceLogin" in text or "Sign in" in text or st == 200:
            return uri
    return None


def b64url(data):
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def random_state():
    return "".join(random.choices(string.ascii_letters + string.digits, k=24))


def read_config():
    cfg = {}
    if os.path.exists(CONFIG):
        with open(CONFIG) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def build_url(client_id, state, challenge, redirect):
    q = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "access_type": "offline",      # get a refresh token
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(q)}"


def exchange(client_id, client_secret, code, code_verifier, redirect):
    # Google's token endpoint wants form encoding, NOT JSON.
    fields = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect,
        "code_verifier": code_verifier,
    }
    return _request_form("POST", TOKEN_URL, fields)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", help="defaults to YT_CLIENT_ID in the config")
    ap.add_argument("--client-secret",
                    help="defaults to YT_CLIENT_SECRET in the config")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    cfg = read_config()
    args.client_id = args.client_id or cfg.get("YT_CLIENT_ID", "")
    args.client_secret = args.client_secret or cfg.get("YT_CLIENT_SECRET", "")

    if not args.client_id or not args.client_secret:
        print("error: need --client-id and --client-secret,")
        print(f"  or YT_CLIENT_ID / YT_CLIENT_SECRET in {CONFIG}")
        return 1

    state = random_state()
    verifier = b64url(os.urandom(48))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())

    print("Checking which redirect URI is registered on the OAuth client...")
    redirect = detect_redirect_uri(args.client_id)
    if not redirect:
        print("\n✗ Could not find a matching redirect URI.")
        print(f"  Tried: {', '.join(REDIRECT_CANDIDATES)}")
        print("\n  Add one of these to the OAuth client:")
        print("    APIs & Services -> Credentials -> your OAuth client ->")
        print("    Authorized redirect URIs -> Add URI")
        print()
        print("  Then run this again.")
        return 1
    print(f"  ✓ registered redirect URI: {redirect}")
    print()

    url = build_url(args.client_id, state, challenge, redirect)

    print("Open this URL, log in as yourself, and approve the request:\n")
    print(f"  {url}\n")
    print("You'll land on a page like")
    print(f"  {redirect}/?code=XXXX&state=YYYY")
    print("Copy the WHOLE address bar URL and paste it below.")
    print("(Ctrl+C to cancel)")

    if not args.no_open:
        subprocess.run(["open", url], check=False)

    print("\nPaste the redirect URL here: ", end="", flush=True)
    try:
        pasted = input().strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 1

    if not pasted:
        print("\nNothing pasted.")
        return 1

    # Accept either a full URL or a bare code.
    code = None
    if pasted.startswith("http"):
        parsed = urllib.parse.urlparse(pasted)
        params = urllib.parse.parse_qs(parsed.query)
        code = (params.get("code") or [None])[0]
        got_state = (params.get("state") or [""])[0]
        if got_state != state:
            print("\n✗ State mismatch -- this URL is from a different "
                  "authorization attempt.")
            print("  expected state: " + state)
            print("  got state     : " + (got_state or "(missing)"))
            print("  (state protects against CSRF, so we won't continue)")
            return 1
    else:
        code = pasted

    if not code:
        print("\n✗ No 'code' found in that URL.")
        print("  The page probably showed an error instead of redirecting.")
        print(f"  The registered redirect URI is: {redirect}")
        return 1

    print(f"\n  authorization code: {code[:8]}...{code[-4:]}")

    status, data = exchange(args.client_id, args.client_secret, code,
                            verifier, redirect)

    if status != 200 or not isinstance(data, dict) or not data.get("access_token"):
        print(f"\n✗ Token exchange failed: HTTP {status}")
        body = json.dumps(data)[:600] if data else ""
        print(f"  {body}")
        if status == 400 and isinstance(data, dict):
            err = data.get("error", "")
            if err == "invalid_grant":
                print("\n  'invalid_grant' usually means the code was already")
                print("  used, or expired (they last ~60s). Run it again.")
            elif err == "redirect_uri_mismatch":
                print(f"\n  The redirect URI must be exactly: {redirect}")
        return 1

    tok = data["access_token"]
    refresh = data.get("refresh_token", "")

    print("\n✓ Got a YouTube access token")
    print(f"  token_type    : {data.get('token_type')}")
    print(f"  expires_in    : {data.get('expires_in')}s")
    print(f"  scope         : {data.get('scope')}")

    # Verify it actually works against the channel.
    headers = {"Authorization": f"Bearer {tok}"}
    key = cfg.get("YT_API_KEY", "")
    if key:
        headers["X-Goog-Api-Key"] = key

    vstatus, vdata = _request("GET", "https://www.googleapis.com/oauth2/v3/tokeninfo",
                               headers=headers)
    if vstatus == 200 and isinstance(vdata, dict):
        print(f"  account       : {vdata.get('email') or vdata.get('sub')}")
    else:
        print("  (could not verify via tokeninfo -- "
              f"HTTP {vstatus})")

    to_write = {"YT_TOKEN": tok}
    if refresh:
        to_write["YT_REFRESH_TOKEN"] = refresh
        print(f"  refresh_token : {refresh[:8]}...{refresh[-4:]}")

    ok, msg = set_values(CONFIG, to_write)
    print()
    if ok:
        print(f"✓ {msg}")
        print("\nNext:  ./stream-meta.sh --check")
    else:
        print(f"! Could not write {CONFIG}: {msg}")
        print("  Add these lines by hand:")
        for k, v in to_write.items():
            print(f"    {k}={v}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
