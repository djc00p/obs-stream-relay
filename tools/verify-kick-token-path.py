#!/usr/bin/env python3
"""Verify the Kick token-exchange path reaches Kick.

The real bug (2026-11-19) was an SSL failure on the direct path:
"certificate verify failed: unable to get local issuer certificate".

Cause: the sandbox sets SSL_CERT_FILE to the egress proxy's trust bundle.
That bundle only has the CAs the proxy needs -- it does NOT have the
issuer for id.kick.com (Google Trust Services WE1). Connecting directly
with that bundle fails TLS.

Fix: direct connections use certifi's full public CA bundle.

This script asserts we get a 4xx from Kick, not a TLS error.

Usage:
    python3 tools/verify-kick-token-path.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request_form

TOKEN_URL = "https://id.kick.com/oauth/token"

failures = []


def check(label, ok, detail=""):
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n          {detail}")
        failures.append(label)


print("=== Kick token-exchange path verification ===\n")

fields = {
    "grant_type": "authorization_code",
    "client_id": "fakeclientid",
    "client_secret": "fakesecret",
    "code": "fakecode",
    "redirect_uri": "https://localhost",
    "code_verifier": "fakestate",
}

status, data = request_form("POST", TOKEN_URL, fields, timeout=20)

print(f"  status = {status}")
print(f"  body   = {str(data)[:200]}")
print()

# A TLS error surfaces as status 0 with an SSL message.
err = str(data).lower() if isinstance(data, dict) else str(data).lower()
is_tls_error = status == 0 and ("ssl" in err or "certificate" in err)

check("no TLS/certificate failure", not is_tls_error, err[:200])
check("reached Kick (got an HTTP status)", status != 0,
      f"status={status} err={err[:200]}")
check("Kick rejected the fake client (4xx)", 400 <= status < 500,
      f"expected 4xx, got {status}")

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
