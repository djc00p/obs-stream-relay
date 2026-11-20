#!/usr/bin/env python3
"""Fetch a Twitch user access token via the OAuth implicit grant.

Prints the authorize URL, opens it in your browser, and has you paste the
redirect URL back. It extracts the token from the fragment.

The redirect URL must be HTTPS (Twitch rejects http://). We use
https://localhost, which is fine because the token arrives in the URL
FRAGMENT -- browsers never send fragments to a server, so nothing needs to
be listening there.

Usage:
    python3 twitch-token.py --client-id YOUR_CLIENT_ID
    python3 twitch-token.py --client-id YOUR_CLIENT_ID --scope channel:manage:broadcast
"""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request as _request
from env_writer import set_values, CONFIG

AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"

DEFAULT_SCOPE = "channel:manage:broadcast"


def validate(token, client_id):
    """Ask Twitch whether the token is valid and what it can do.

    Returns (status, info). status 0 means the network call failed (proxy,
    offline) -- which is NOT the same as the token being rejected.
    """
    status, data = _request(
        "GET", VALIDATE_URL,
        headers={"Authorization": f"OAuth {token}"},
        timeout=15,
    )
    return status, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", help="defaults to TWITCH_CLIENT_ID in the config")
    ap.add_argument("--scope", default=DEFAULT_SCOPE)
    ap.add_argument("--no-open", action="store_true",
                    help="don't open a browser, just print the URL")
    args = ap.parse_args()

    # Fall back to the client id already in the config.
    if not args.client_id:
        cfg = {}
        if os.path.exists(CONFIG):
            with open(CONFIG) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        cfg[k.strip()] = v.strip().strip('"').strip("'")
        args.client_id = cfg.get("TWITCH_CLIENT_ID", "")

    if not args.client_id:
        print(f"error: need --client-id, or TWITCH_CLIENT_ID in {CONFIG}")
        return 1

    # A state parameter protects against CSRF: without it, a crafted
    # URL carrying an attacker's token could be pasted into this tool
    # and stored as if it were the operator's own.
    #
    # Twitch's implicit flow has no PKCE, so state is the ONLY
    # protection here -- unlike the Kick and YouTube helpers, where the
    # PKCE verifier does that job.
    state = secrets.token_urlsafe(16)

    params = {
        "client_id": args.client_id,
        "redirect_uri": "https://localhost",
        "response_type": "token",
        "scope": args.scope,
        "state": state,
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print("Open this URL, log in as yourself, and click Authorize:\n")
    print(f"  {url}\n")
    print("You'll land on a page like")
    print("  https://localhost/#access_token=XXXX&state=YYYY")
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

    token = None
    # Try the fragment first (implicit grant).
    if "#" in pasted:
        frag = urllib.parse.parse_qs(pasted.split("#", 1)[1])
        token = frag.get("access_token", [None])[0]
        if frag.get("error"):
            print(f"\nerror: Twitch returned {frag.get('error')[0]}")
            if frag.get("error_description"):
                print(f"       {frag['error_description'][0]}")
            return 1

        # Verify the state. A MISSING state is rejected too -- this
        # flow has no PKCE, so state is the only CSRF protection.
        got_state = (frag.get("state") or [""])[0]
        if got_state != state:
            print("\nerror: state mismatch -- this URL is not from this run.")
            print(f"       expected state: {state}")
            print(f"       got state     : {got_state or '(missing)'}")
            print("       (state protects against CSRF, so we won't continue)")
            return 1

    # Also handle the case where they pasted just the token value.
    if not token and re.fullmatch(r"[A-Za-z0-9_\-]{20,}", pasted):
        print("\nerror: that is a bare token, not the redirect URL.")
        print("       Paste the whole address-bar URL so the state can be")
        print("       checked -- a bare token has no state to verify.")
        return 1

    # Or a full code (authorization code flow) -- not what we want, but
    # report it clearly instead of failing cryptically.
    if not token:
        if "code=" in pasted:
            print("\nerror: that URL contains an authorization CODE, not a token.")
            print("       That means the authorize URL used response_type=code")
            print("       instead of response_type=token.")
            print("       Re-run with the URL this script printed.")
            return 1
        print("\nerror: no access_token found in that URL.")
        print("       Paste the full address-bar URL, including the # part.")
        return 1

    print(f"\ntoken captured ({len(token)} chars): {token[:8]}...{token[-4:]}")

    status, info = validate(token, args.client_id)
    user_id = info.get("user_id") if isinstance(info, dict) else None

    if status == 200:
        print("\n✓ Twitch says this token is VALID")
        print(f"  client_id : {info.get('client_id')}")
        print(f"  user_id   : {info.get('user_id')}")
        print(f"  login     : {info.get('login')}")
        print(f"  scopes    : {info.get('scopes')}")
        expires = info.get("expires_in")
        if expires:
            print(f"  expires in: {expires}s")
    elif status == 0:
        print("\n! Could not reach Twitch to validate the token")
        print(f"  {info.get('error') if isinstance(info, dict) else info}")
        print("  The token WAS captured. This is a network problem reaching")
        print("  id.twitch.tv, not a token problem.")
    else:
        print(f"\n✗ Twitch rejected the token: HTTP {status}")
        print(f"  {json.dumps(info) if isinstance(info, dict) else info}")
        print("\n  If the error is 'invalid token', run this script again to get a")
        print("  fresh one. If it's a scope problem, add channel:manage:broadcast.")
        return 1

    # Write the credentials straight into the config.
    to_write = {
        "TWITCH_CLIENT_ID": args.client_id,
        "TWITCH_TOKEN": token,
    }
    if user_id:
        to_write["TWITCH_USER_ID"] = str(user_id)

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
