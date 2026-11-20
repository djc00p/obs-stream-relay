"""Verify the YouTube OAuth path is reachable from this machine.

Checks:
  1. accounts.google.com is reachable (the auth page)
  2. oauth2.googleapis.com/token is reachable (the exchange endpoint)
  3. A deliberately-bad exchange returns a proper OAuth error (not a
     network/TLS failure) -- proving the request actually lands.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request as _request
from proxy_http import request_form as _request_form

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

failures = []


def check(label, ok, detail=""):
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n          {detail}")
        failures.append(label)


print("=== YouTube OAuth path verification ===\n")

# 1. Auth endpoint.
st, body = _request("GET", AUTH_URL, timeout=20)
check("accounts.google.com reachable", st in (200, 302, 400),
      f"HTTP {st}")
print(f"        (HTTP {st})")

# 2. Token endpoint reachable. A GET returns 404 because the endpoint is
#    POST-only -- that still proves we reached the host.
st, body = _request("GET", TOKEN_URL, timeout=20)
check("oauth2.googleapis.com reachable", st in (200, 400, 404, 405),
      f"HTTP {st}")
print(f"        (HTTP {st} -- GET on a POST-only endpoint)")

# 3. A real exchange attempt with a fake code. Google validates the
#    client before the code, so this returns 401 invalid_client. That is
#    a successful round trip: it proves the request landed AND that our
#    form encoding was accepted.
st, data = _request_form("POST", TOKEN_URL, {
    "client_id": "fake-client-id",
    "client_secret": "fake-secret",
    "code": "fake-code",
    "grant_type": "authorization_code",
    "redirect_uri": "http://localhost",
})
check("exchange request lands on Google", st != 0, "no HTTP status returned")
check("Google validates the client (401 invalid_client)",
      st == 401, f"expected 401, got {st}")
check("response is an OAuth error body",
      isinstance(data, dict) and "error" in data,
      repr(data)[:200])
if isinstance(data, dict):
    print(f"        error: {data.get('error')}")
    # If our form encoding were broken we'd see invalid_request instead.
    check("form encoding accepted (not invalid_request)",
          data.get("error") != "invalid_request",
          "Google says our request body was malformed")

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
