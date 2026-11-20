#!/usr/bin/env python3
"""Scan the relay tree for anything that identifies a specific person.

The published repo must be usable by a stranger. Anything that names a
person, a channel, a machine, a project, or a secret has to be either
removed or replaced with a placeholder.

Usage:
    python3 tools/scan-for-pii.py <root-dir>
"""

import os
import re
import sys

# Patterns that must not appear in a published file.
PATTERNS = [
    # --- names / handles ---
    (r"YOUR_HANDLE", "personal channel handle"),
    (r"your-handle", "personal channel handle"),
    (r"the", "personal name"),
    (r"You", "personal name"),
    (r"2kingd", "email local part"),
    (r"coop2395", "email local part"),
    (r"deonte\.cooper", "email local part"),
    (r"DJCoop", "username"),
    (r"djcoop", "username"),
    # --- channel ids ---
    (r"UCxxxxxxxxxxxxxxxxxxxxxx", "YouTube channel id"),
    (r"12345678", "Twitch user id"),
    (r"12345678", "Kick user id"),
    # --- machine / local paths ---
    (r"$HOME", "absolute local path"),
    (r"MacBook-Pro-2", "machine name"),
    (r"com\.djcoop", "launchd label"),
    # --- app names / projects ---
    (r"OBS Stream Relay", "project name"),
    (r"Stream Relay", "project name (may be intentional -- review)"),
    # --- secrets ---
    (r"GOCSPX-[A-Za-z0-9_\-]+", "Google OAuth client secret"),
    (r"AIzaSy[A-Za-z0-9_\-]{20,}", "Google API key"),
    (r"ya29\.[A-Za-z0-9_\-\.]+", "Google OAuth access token"),
    (r"1//0f[A-Za-z0-9_\-]+", "Google OAuth refresh token"),
    (r"YTU4ZTHK[A-Za-z0-9_\-\.]+", "Kick access token"),
    (r"g0dws9aj[A-Za-z0-9_\-]+", "Twitch access token"),
    (r"6hvel94b6fzcan2l7w0szialt9dm2e", "Twitch client id"),
    (r"01M7VQNYYQR1Z7SA6K48DVYEN6", "Kick client id"),
    (r"c5be2da22d4e73ba8874e0164e78627669109c58522b555a8ba05605d6ff5ef5",
     "Kick client secret"),
    (r"live_[0-9]+_[A-Za-z0-9]+", "Twitch stream key"),
    (r"sk_[a-z]+-[0-9]_[A-Za-z0-9]+", "Kick stream key"),
    (r"j8s8-xmtm", "YouTube stream key"),
    (r"frbr-f3m9", "YouTube stream key"),
]

# Binary / large / generated files to skip.
SKIP_DIRS = {"__pycache__", "test-out", ".git", "node_modules", "preview"}
SKIP_SUFFIX = {".log", ".pyc", ".pid", ".crt", ".key", ".tar.gz", ".tgz"}
SKIP_NAMES = {"mediamtx", "mediamtx.log", "mediamtx.err.log", "mediamtx.pid",
              "checksums.txt"}


def should_skip(name):
    if name in SKIP_NAMES:
        return True
    if any(name.endswith(s) for s in SKIP_SUFFIX):
        return True
    return False


def scan(root):
    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if should_skip(fn):
                continue
            path = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(path) > 2_000_000:
                    continue
                with open(path, "r", errors="ignore") as f:
                    text = f.read()
            except OSError:
                continue

            rel = os.path.relpath(path, root)
            for pat, why in PATTERNS:
                for m in re.finditer(pat, text):
                    line_no = text[:m.start()].count("\n") + 1
                    line = text.splitlines()[line_no - 1] if \
                        line_no <= len(text.splitlines()) else ""
                    findings.append((rel, line_no, why, m.group(0)[:60],
                                     line.strip()[:100]))
    return findings


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    findings = scan(root)

    if not findings:
        print("No personal information found.")
        return 0

    by_why = {}
    for rel, ln, why, match, line in findings:
        by_why.setdefault(why, []).append((rel, ln, match, line))

    print(f"=== {len(findings)} finding(s) ===\n")
    for why in sorted(by_why):
        items = by_why[why]
        files = sorted({i[0] for i in items})
        print(f"[{why}]  {len(items)} hit(s) in {len(files)} file(s)")
        for rel, ln, match, line in items[:6]:
            print(f"    {rel}:{ln}")
            print(f"        {line}")
        if len(items) > 6:
            print(f"        ... and {len(items) - 6} more")
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
