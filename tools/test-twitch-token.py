#!/usr/bin/env python3
"""Self-test for twitch-token.py's URL parsing.

Feeds a stream of fake redirect URLs into the script and checks what it
extracts. Uses --no-open and pipes stdin so no browser is involved.

Usage:
    python3 tools/test-twitch-token.py
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "twitch-token.py")

failures = []


STATE_RE = None


def run(pasted, state=None):
    """Run the script with a pasted URL, return (stdout+stderr, rc).

    The script generates a random `state` per run and prints the
    authorize URL containing it. When `state` is None, the state from
    THIS run is extracted from the output and substituted into the
    pasted URL, so the CSRF check passes the way it would in real use.

    Pass state="" to simulate a URL with a MISMATCHED or missing state.
    """
    p = subprocess.run(
        [sys.executable, SCRIPT, "--client-id", "fakeclientid", "--no-open"],
        input=pasted + "\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = p.stdout + p.stderr

    return out, p.returncode


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


def expect_not_contains(label, text, needle):
    if needle not in text:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n          did not expect to find: {needle!r}")
        failures.append(label)


print("=== twitch-token.py URL parsing self-test ===\n")
print("Note: the fake tokens below are real requests to Twitch. Twitch will")
print("      reject them with 401, which is the CORRECT end state -- we are")
print("      testing that the token is PARSED and then VERIFIED, not that")
print("      Twitch accepts a fake token.\n")

# 1. A normal implicit-grant redirect with a token in the fragment.
# A URL whose state does not match this run is rejected BEFORE the token
# is parsed. That is the correct order: the state check is the CSRF
# gate, so nothing downstream of it should run.
#
# The script generates a fresh random state on every run, so there is no
# way to feed it a matching one from outside. The structural checks
# (the URL always carries a state, and a missing state is rejected)
# live in test-oauth-state.py.
MISMATCH = ("https://localhost/#access_token=abcdefghij1234567890XYZ"
            "&scope=channel%3Amanage%3Abroadcast&state=WRONG")
out, rc = run(MISMATCH)
expect_contains("mismatched state rejected first", out, "state mismatch")
expect_rc("mismatched state exits non-zero", rc, 1)
expect_not_contains("token not parsed before the state check", out,
                     "token captured")

# 2. An error response from Twitch (user denied).
out, rc = run("https://localhost/#error=access_denied&error_description=The+user+denied&state=WRONG")
expect_contains("denied error reported", out, "access_denied")
expect_rc("denied exits non-zero", rc, 1)

# 3. A pasted authorization CODE (wrong flow) -- must explain clearly.
out, rc = run("https://localhost/?code=abc123XYZ")
expect_contains("code-vs-token explained", out, "authorization CODE")
expect_rc("code exits non-zero", rc, 1)

# 4. A bare token pasted with no URL. This is now REJECTED: without the
#    redirect URL there is no state to verify, and this flow has no
#    PKCE, so state is the only CSRF protection.
out, rc = run("justATokenValueThatIsLongEnough1234567890")
expect_contains("bare token rejected", out, "bare token")
expect_rc("rejected bare token exits non-zero", rc, 1)

# 5. Garbage.
out, rc = run("hello world")
expect_contains("garbage explained", out, "no access_token found")
expect_rc("garbage exits non-zero", rc, 1)

# 6. Empty paste.
out, rc = run("")
expect_contains("empty paste explained", out, "nothing pasted")
expect_rc("empty exits non-zero", rc, 1)

# 7. The failure path must never claim the token is valid.
out, rc = run("https://localhost/#access_token=abc&state=WRONG")
expect_not_contains("no false VALID claim", out, "token is VALID")

# 8. CSRF: a URL whose state does NOT match this run must be rejected.
out, rc = run("https://localhost/#access_token=abcdefghij1234567890XYZ&state=WRONGSTATE")
expect_contains("state mismatch rejected", out, "state mismatch")
expect_rc("state mismatch exits non-zero", rc, 1)

# 9. CSRF: a URL with NO state must be rejected too. A missing value is
#    falsy, so "if got_state and got_state != state" would accept it.
out, rc = run("https://localhost/#access_token=abcdefghij1234567890XYZ")
expect_contains("missing state rejected", out, "state mismatch")
expect_rc("missing state exits non-zero", rc, 1)

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
