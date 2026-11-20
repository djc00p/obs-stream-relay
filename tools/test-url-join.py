#!/usr/bin/env python3
"""Test that a trailing slash on a forward URL does not double the slash.

Instagram's ingest URL comes with a trailing slash:
    rtmps://host:443/rtmp/
and the stream key is appended as a path segment:
    rtmps://host:443/rtmp/<key>

MediaMTX splits a forward dest on '#':
    <base>#<key>
so a trailing slash on the base produces an EMPTY path segment and the
platform rejects it:
    rtmp://host/path/#KEY   ->   /path//KEY   ->   "Invalid URL"

Verified against MediaMTX v1.21.4: it logs the base URL it uses
("forwarding to 'rtmp://host/path/'"), and with the key appended the
published path carries the double slash.

This test asserts that every place that joins a URL and a key strips a
trailing slash first.

Usage:
    python3 tools/test-url-join.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def find(rel):
    """Find a script in either layout.

    The live working copy has the operator scripts at its root; the
    published repo puts them in scripts/. The test has to work in
    both.
    """
    for cand in (os.path.join(ROOT, rel),
                 os.path.join(ROOT, "scripts", rel)):
        if os.path.exists(cand):
            return cand
    return None

failures = []


def check(label, ok, detail=""):
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}")
        if detail:
            print(f"          {detail}")
        failures.append(label)


print("=== url + key joining: no double slash ===\n")

# 1. The shell scripts that build "$url/$key" by hand.
print("-- shell: url + key joins --")
for rel in ("dry-run.sh", "refresh-keys.sh", "tools/rtmp-probe.sh"):
    path = find(rel)
    if not path:
        check(f"{rel} exists", False, rel)
        continue
    with open(path) as f:
        text = f.read()

    # Find every "$url/$key" style join.
    joins = re.findall(r'\$\{?(\w+)\}?/\$\{?(\w+)\}?', text)
    bad = []
    for base, key in joins:
        # The base must be stripped of a trailing slash.
        # "${url%/}/$key" is the safe form.
        if f"${{{base}%/}}" not in text:
            bad.append(f"{base}/{key}")
    check(f"{rel}: every url+key join strips a trailing slash",
          not bad, f"unstripped: {bad}")

print()
print("-- shell: rtmp-probe FULL --")
p = find("tools/rtmp-probe.sh")
if p:
    with open(p) as f:
        text = f.read()
    check("rtmp-probe uses ${URL%/}/${KEY}",
          '${URL%/}/${KEY}' in text,
          "the FULL= line does not strip the trailing slash")

print()
print("-- python: relay.sh's dest builder --")
p = find("relay.sh")
if p:
    with open(p) as f:
        text = f.read()
    check("relay.sh strips the trailing slash from the url",
          "url.rstrip" in text or 'url=url.rstrip' in text,
          "no rstrip on the url before building the dest")

print()
print("=== the shell form itself behaves ===")
# Prove ${url%/} strips exactly one trailing slash and leaves the
# rest alone.
import subprocess
cases = [
    ("rtmps://host:443/rtmp/", "rtmps://host:443/rtmp"),
    ("rtmps://host:443/rtmp", "rtmps://host:443/rtmp"),
    ("rtmp://host/path//", "rtmp://host/path/"),
]
for base, expected in cases:
    script = f'url="{base}"; printf "%s" "${{url%/}}"'
    out = subprocess.run(["bash", "-c", script], capture_output=True,
                         text=True).stdout
    check(f"{base} -> {expected}", out == expected, f"got {out!r}")

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
