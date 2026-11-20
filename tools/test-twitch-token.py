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


def run(pasted):
    """Run the script with a pasted URL, return (stdout+stderr, rc)."""
    p = subprocess.run(
        [sys.executable, SCRIPT, "--client-id", "fakeclientid", "--no-open"],
        input=pasted + "\n",
        capture_output=True,
        text=True,
        timeout=30,
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
GOOD = "https://localhost/#access_token=abcdefghij1234567890XYZ&scope=channel%3Amanage%3Abroadcast&token_type=bearer"
out, rc = run(GOOD)
# The script prints the token truncated: first 8 + "..." + last 4.
expect_contains("fragment token extracted", out, "abcdefgh...0XYZ")
expect_contains("token length reported", out, "23 chars")
# Twitch will 401 the fake token -> non-zero exit, and it must SAY why.
expect_contains("rejection explained", out, "rejected")
expect_rc("rejected token exits non-zero", rc, 1)

# 2. An error response from Twitch (user denied).
out, rc = run("https://localhost/#error=access_denied&error_description=The+user+denied")
expect_contains("denied error reported", out, "access_denied")
expect_rc("denied exits non-zero", rc, 1)

# 3. A pasted authorization CODE (wrong flow) -- must explain clearly.
out, rc = run("https://localhost/?code=abc123XYZ")
expect_contains("code-vs-token explained", out, "authorization CODE")
expect_rc("code exits non-zero", rc, 1)

# 4. A bare token pasted with no URL.
out, rc = run("justATokenValueThatIsLongEnough1234567890")
expect_contains("bare token extracted", out, "justATok...7890")
expect_contains("bare token length reported", out, "41 chars")
expect_rc("rejected bare token exits non-zero", rc, 1)

# 5. Garbage.
out, rc = run("hello world")
expect_contains("garbage explained", out, "no access_token found")
expect_rc("garbage exits non-zero", rc, 1)

# 6. Empty paste.
out, rc = run("")
expect_contains("empty paste explained", out, "nothing pasted")
expect_rc("empty exits non-zero", rc, 1)

# 7. A token that Twitch actually accepts would exit 0 -- we can't test that
#    without a real credential, but we can confirm the success branch prints
#    the right things by checking the code path is reachable.
out, rc = run("https://localhost/#access_token=abc")
expect_contains("short token still parsed", out, "token captured")
expect_not_contains("no false VALID claim", out, "token is VALID")

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
