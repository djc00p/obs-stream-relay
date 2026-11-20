#!/usr/bin/env python3
"""Get a Kick access token via OAuth 2.1 Authorization Code + PKCE.

Kick's OAuth differs from Twitch's in three important ways:

1. The OAuth endpoint is **id.kick.com**, not api.kick.com.
2. It uses the **authorization code** flow, not the implicit flow. The
   callback carries `?code=...&state=...` in the QUERY string, not a token
   in the fragment.
3. **PKCE is required** -- you must send `code_challenge` (S256 of a random
   verifier) and `code_challenge_method=S256`.

And because it's the code flow, you need a **client_secret** as well. Kick
issues one when you create the app, even for public clients.

Verified against https://api.kick.com/swagger/doc.yaml on 2026-11-19.

Usage:
    python3 kick-token.py --client-id X --client-secret Y
    python3 kick-token.py --client-id X --client-secret Y --no-open
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request as _request
from proxy_http import request_form as _request_form
from env_writer import set_values, CONFIG

AUTH_URL = "https://id.kick.com/oauth/authorize"
TOKEN_URL = "https://id.kick.com/oauth/token"
REDIRECT_URI = "https://localhost"

# Only what we need. channel:read  -> GET channel info
#               channel:write -> PATCH title/category
DEFAULT_SCOPE = "channel:read channel:write user:read"


def b64url(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_pkce():
    """Return (code_verifier, code_challenge)."""
    verifier = b64url(os.urandom(32))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def token_request(client_id, client_secret, code, verifier):
    """Exchange the authorization code for an access token.

    Kick's token endpoint wants application/x-www-form-urlencoded, NOT
    JSON, so this uses the form-encoded helper.
    """
    body = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }
    return _request_form("POST", TOKEN_URL, body, timeout=20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", help="defaults to KICK_CLIENT_ID in the config")
    ap.add_argument("--client-secret",
                    help="defaults to KICK_CLIENT_SECRET in the config")
    ap.add_argument("--scope", default=DEFAULT_SCOPE)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    # Fall back to the credentials already in the config, so this is a
    # one-command run once the app is registered.
    if not args.client_id or not args.client_secret:
        cfg = {}
        if os.path.exists(CONFIG):
            with open(CONFIG) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        cfg[k.strip()] = v.strip().strip('"').strip("'")
        args.client_id = args.client_id or cfg.get("KICK_CLIENT_ID", "")
        args.client_secret = args.client_secret or cfg.get("KICK_CLIENT_SECRET", "")

    if not args.client_id or not args.client_secret:
        print("error: need --client-id and --client-secret.")
        print("  Or put them in %s as KICK_CLIENT_ID / KICK_CLIENT_SECRET." % CONFIG)
        return 1

    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id": args.client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": args.scope,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print("Open this URL, log in as yourself, and approve the request:\n")
    print(f"  {url}\n")
    print("You'll land on a page like")
    print("  https://localhost/?code=XXXX&state=YYYY")
    print("Copy the WHOLE address bar URL and paste it below.")
    print("(Ctrl+C to cancel)\n")

    if not args.no_open:
        try:
            subprocess.run(["open", url], check=False)
        except Exception:
            pass

    print("Paste the redirect URL here: ", end="", flush=True)
    try:
        pasted = input().strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\ncancelled.")
        return 1

    if not pasted:
        print("\nerror: nothing pasted.")
        return 1

    # Pull code + state out of the query string.
    query = pasted.split("?", 1)[1] if "?" in pasted else pasted
    q = urllib.parse.parse_qs(query)
    code = q.get("code", [None])[0]
    got_state = q.get("state", [None])[0]
    err = q.get("error", [None])[0]

    if err:
        print(f"\nerror: Kick returned {err}")
        if q.get("error_description"):
            print(f"       {q['error_description'][0]}")
        return 1

    if not code:
        print("\nerror: no 'code' found in that URL.")
        print("       Paste the full address-bar URL including the ? part.")
        print("       (If you used the Twitch implicit URL, the token would be")
        print("        in the # fragment -- Kick uses ?code= instead.)")
        return 1

    if got_state != state:
        print("\nerror: state mismatch -- this may not be the URL from this run.")
        print(f"       expected state: {state}")
        print(f"       got state     : {got_state or '(missing)'}")
        print("       (state protects against CSRF, so we won't continue)")
        return 1

    print(f"\ncode captured ({len(code)} chars): {code[:8]}...{code[-4:]}")

    status, data = token_request(args.client_id, args.client_secret, code, verifier)

    if status == 200 and isinstance(data, dict) and data.get("access_token"):
        tok = data["access_token"]
        print("\n✓ Got a Kick access token")
        print(f"  token_type    : {data.get('token_type')}")
        print(f"  expires_in    : {data.get('expires_in')}s")
        print(f"  refresh_expires_in : {data.get('refresh_expires_in')}s")
        print(f"  scope         : {data.get('scope')}")
        print(f"  token         : {tok[:8]}...{tok[-4:]}")

        # Write the credentials straight into the config. Printing them
        # for manual copy-paste is how the wrong value ended up in the
        # file once already.
        to_write = {
            "KICK_TOKEN": tok,
            "KICK_CLIENT_ID": args.client_id,
            "KICK_CLIENT_SECRET": args.client_secret,
        }
        if data.get("refresh_token"):
            to_write["KICK_REFRESH_TOKEN"] = data["refresh_token"]

        ok, msg = set_values(CONFIG, to_write)
        if ok:
            print(f"\n✓ {msg}")
            print("\nNext:  ./stream-meta.sh --check")
        else:
            print(f"\n! Could not write {CONFIG}: {msg}")
            print("  Add these lines by hand:")
            for k, v in to_write.items():
                print(f"    {k}={v}")
        return 0 if ok else 1

    print(f"\n✗ Token exchange failed: HTTP {status}")
    print(f"  {json.dumps(data) if isinstance(data, dict) else str(data)[:400]}")
    print()
    print("  If it says 'invalid_grant', the code was already used or the")
    print("  redirect_uri / code_verifier did not match. Re-run this script.")
    print("  If it says 'invalid_client', check the client_id and client_secret.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
