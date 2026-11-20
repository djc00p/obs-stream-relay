#!/usr/bin/env python3
"""Tests for the OAuth CSRF protection in the token helpers.

The `state` parameter exists so that a crafted URL carrying someone
else's authorization code cannot be pasted into the tool and stored as
if it were the operator's own.

Three things must hold for every helper:

  1. the authorize URL includes a state parameter
  2. a URL with a MISMATCHED state is rejected
  3. a URL with a MISSING state is rejected

(3) is the one that was wrong. `if got_state and got_state != state`
accepts a missing state, because a missing value is falsy and the
condition short-circuits.

Twitch matters most: its implicit flow has no PKCE and no client
secret, so state is the ONLY protection.

Usage:
    python3 tools/test-oauth-state.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

failures = []


def check(label, ok, detail=""):
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n          {detail}")
        failures.append(label)


HELPERS = {
    "twitch-token.py": "twitch",
    "kick-token.py": "kick",
    "youtube-token.py": "youtube",
}

print("=== OAuth state (CSRF) protection ===\n")

for filename, platform in HELPERS.items():
    path = os.path.join(HERE, filename)
    if not os.path.exists(path):
        check(f"{filename} exists", False, f"missing: {path}")
        continue

    with open(path) as f:
        text = f.read()

    # 1. the authorize URL carries a state.
    has_state_in_url = re.search(r'["\']state["\']\s*:', text) is not None
    check(f"{platform}: authorize URL includes state", has_state_in_url)

    # 2 and 3. the comparison must REJECT a missing state.
    # The old form was:  if got_state and got_state != state:
    # The safe form is:  if got_state != state:
    rejects_missing = re.search(
        r"if\s+got_state\s*!=\s*state\s*:", text) is not None
    accepts_missing = re.search(
        r"if\s+got_state\s+and\s+got_state\s*!=\s*state\s*:", text) is not None
    check(f"{platform}: missing state is rejected", rejects_missing,
          "no 'if got_state != state' check found")
    check(f"{platform}: does not accept a missing state",
          not accepts_missing,
          "found 'if got_state and got_state != state' -- a missing "
          "state is falsy, so it would be accepted")

    # The error message should say what happened.
    mentions_missing = "missing" in text.lower()
    check(f"{platform}: error message mentions a missing state",
          mentions_missing)

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
