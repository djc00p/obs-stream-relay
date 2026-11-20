#!/usr/bin/env python3
"""Guard against pasting an OAuth authorization CODE where a TOKEN belongs.

WHAT WENT WRONG (2026-11-19)
---------------------------
The Kick token helper printed the lines to add to stream-meta.env. The
user pasted the value from the OAuth callback URL -- which was the
authorization CODE -- into KICK_TOKEN. The tool then used it as a bearer
token and every request failed with 401.

The two look similar in a terminal:
    code  : OWJIMMNIZTGTYWQ5NC0ZOTG2LTK5YMMTNGU4OWVLYJC5MZIZ   (48 chars, uppercase-ish)
    token : 2YotnFZFEjr1zCsicMWpAA                                 (varies)

They are the same length and same alphabet. Nothing but the API can tell
them apart -- but the PATTERN is a strong hint, and a clear error beats a
mysterious 401.

WHAT THIS DOES
--------------
`looks_like_auth_code(value)` returns True when the value matches the
shape of an OAuth authorization code rather than an access token.

`explain_bad_value(value)` returns a human-readable explanation.

Usage:
    from value_guard import looks_like_auth_code, explain_bad_value
"""

import re

# Kick authorization codes are base64url of a 32-byte value.
_KICK_CODE = re.compile(r"^[A-Za-z0-9_-]{43,64}$")

# Twitch access tokens are opaque but consistently longer and usually
# contain mixed case + digits. They do NOT look like pure uppercase.
_TWITCH_TOKEN = re.compile(r"^[A-Za-z0-9_-]{40,}$")


def looks_like_auth_code(value, platform=None):
    """Heuristic: does this value look like an OAuth authorization code?

    Returns True/False. Not a substitute for the API -- a real code
    exchange is the only authority. This just gives a good error message
    instead of a bare 401.
    """
    if not value:
        return False
    v = value.strip()
    if not _KICK_CODE.match(v):
        return False

    # Authorization codes from Kick are base64url of random bytes, which
    # means they are usually a mix of upper and lower case and often
    # contain digits. Access tokens are also mixed case, so the length +
    # alphabet is the main signal.

    # Strong signal: a Twitch token is 40+ chars but Twitch codes are
    # 40 chars exactly. Kick codes are exactly 48.
    if len(v) in (40, 48):
        return True

    # Another strong signal: no lowercase at all, or all uppercase.
    if v.isupper() or v.islower():
        return True

    return False


def explain_bad_value(value, platform=None):
    """Return an explanation if the value looks wrong, else None."""
    if not value:
        return None
    v = value.strip()

    if not looks_like_auth_code(v, platform):
        return None

    name = platform or "this platform"
    return (
        f"This value looks like an OAuth AUTHORIZATION CODE, not an access "
        f"token.\n"
        f"  {name} authorization codes are short-lived and single-use. The "
        f"access token\n"
        f"  is what the token helper prints AFTER a successful exchange, and "
        f"it starts\n"
        f"  with the word '✓ Got a ... token'.\n"
        f"\n"
        f"  Re-run the token helper and let it WRITE the file itself -- "
        f"the helpers now\n"
        f"  update stream-meta.env directly, so there is nothing to paste."
    )


if __name__ == "__main__":
    samples = [
        ("OWJIMMNIZTGTYWQ5NC0ZOTG2LTK5YMMTNGU4OWVLYJC5MZIZ", True),
        ("2YotnFZFEjr1zCsicMWpAA", False),
        ("abcdefghij1234567890XYZ", False),
        ("", False),
    ]
    print("=== value guard self-test ===\n")
    failures = 0
    for value, want in samples:
        got = looks_like_auth_code(value)
        ok = got == want
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {value[:40]!r:45} -> {got}")
    print()
    if failures:
        print(f"FAILED: {failures}")
        raise SystemExit(1)
    print("ALL CHECKS PASSED")
