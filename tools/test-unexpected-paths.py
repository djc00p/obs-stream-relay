#!/usr/bin/env python3
"""Self-test for unexpected-paths.py.

Builds synthetic API payloads and asserts the detector behaves correctly:

  1. only land/vert paths           -> no output, exit 0
  2. an extra 'vertical/land' path  -> listed, exit 0 (caller checks output)
  3. an extra 'testdummy/foo' path  -> listed
  4. land/vert with deep sub-paths  -> still clean (land/land, vert/vert)
  5. the known 'all_others' entry   -> ignored

Usage:
    python3 tools/test-unexpected-paths.py
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "unexpected-paths.py")

failures = []


def run(payload):
    """Feed a payload to the detector via stdin, return (stdout, exit)."""
    p = subprocess.run(
        [sys.executable, TOOL],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    return p.stdout.strip(), p.returncode


def check(label, got, want):
    if got == want:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n          got:  {got!r}\n          want: {want!r}")
        failures.append(label)


def path(name, w=1920, h=1080):
    return {
        "name": name,
        "ready": True,
        "tracks2": [
            {"kind": "video", "codecProps": {"width": w, "height": h}},
        ],
    }


print("=== unexpected-paths.py self-test ===\n")

# 1. clean
out, rc = run({"items": [path("land/land"), path("vert/vert")]})
check("clean: no output", out, "")
check("clean: exit 0", rc, 0)

# 2. known extra
out, rc = run({"items": [path("land/land"), path("vert/vert"),
                          path("vertical/land", 1080, 1920)]})
check("extra vertical/land: listed", out, "vertical/land\t1080x1920")

# 3. unknown extra
out, rc = run({"items": [path("land/land"), path("testdummy/dummykey")]})
check("extra testdummy: listed", out, "testdummy/dummykey\t1920x1080")

# 4. deep sub-paths under land/vert are still clean
out, rc = run({"items": [path("land/land"), path("land/extra"),
                          path("vert/vert"), path("vert/anything")]})
check("land/vert sub-paths: clean", out, "")

# 5. all_others is ignored
out, rc = run({"items": [path("all_others"), path("land/land")]})
check("all_others: ignored", out, "")

# 6. empty payload
out, rc = run({"items": []})
check("empty: no output", out, "")
check("empty: exit 0", rc, 0)

# 7. a path with no video track still gets listed
out, rc = run({"items": [{"name": "weird/thing", "ready": False}]})
check("no-video path: listed", out, "weird/thing\tno-video")

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
