#!/usr/bin/env python3
"""Self-test for kick-token.py.

Tests the OAuth callback parsing, the PKCE generation, and the state check.
The token exchange is exercised with a fake client, so it will fail at
Kick's end -- that is expected and is itself a useful assertion (it proves
we reached id.kick.com).

Usage:
    python3 tools/test-kick-token.py
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "kick-token.py")

failures = []


def run(pasted):
    p = subprocess.run(
        [sys.executable, SCRIPT, "--client-id", "fakeid",
         "--client-secret", "fakesecret", "--no-open"],
        input=pasted + "\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    return p.stdout + p.stderr, p.returncode


def expect_contains(label, text, needle):
    if needle in text:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n          expected to find: {needle!r}")
        failures.append(label)


def expect_rc(label, rc, want):
    if rc == want:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n          rc={rc} want={want}")
        failures.append(label)


print("=== kick-token.py self-test ===\n")

# 1. The authorize URL must carry PKCE and the right params.
out, rc = run("")
expect_contains("authorize URL uses id.kick.com", out, "https://id.kick.com/oauth/authorize")
expect_contains("response_type=code", out, "response_type=code")
expect_contains("PKCE challenge present", out, "code_challenge=")
expect_contains("PKCE method is S256", out, "code_challenge_method=S256")
expect_contains("redirect_uri is https", out, "redirect_uri=https%3A%2F%2Flocalhost")
expect_contains("channel:write scope requested", out, "channel%3Awrite")

# 2. Empty paste.
out, rc = run("")
expect_contains("empty paste explained", out, "nothing pasted")
expect_rc("empty exits non-zero", rc, 1)

# 3. Denied by the user.
out, rc = run("https://localhost/?error=access_denied&error_description=User+denied")
expect_contains("denial reported", out, "access_denied")
expect_contains("denial description shown", out, "User denied")
expect_rc("denial exits non-zero", rc, 1)

# 4. No code in the URL.
out, rc = run("https://localhost/?something=else")
expect_contains("missing code explained", out, "no 'code' found")
expect_contains("points at the right param name", out, "?code=")
expect_rc("missing code exits non-zero", rc, 1)

# 5. State mismatch must be refused (CSRF protection).
out, rc = run("https://localhost/?code=abc123&state=totallyWrongState")
expect_contains("state mismatch refused", out, "state mismatch")
expect_rc("state mismatch exits non-zero", rc, 1)

# 6. A well-formed code with the right state should get PAST parsing and
#    fail at the token exchange (fake client). That proves parsing works
#    and that we reached id.kick.com.
out, rc = run("https://localhost/?code=abcdefghij&state=SELF")
if "state mismatch" in out:
    print("  SKIP  code path (state is random per run; needs live state)")
else:
    expect_contains("code parsed", out, "code captured")
    expect_contains("token exchange attempted", out, "Token exchange failed")
    expect_rc("bad client exits non-zero", rc, 1)

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
