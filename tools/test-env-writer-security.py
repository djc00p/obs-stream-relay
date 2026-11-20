#!/usr/bin/env python3
"""Tests for the credential-file security properties.

These are the properties that matter when the file holds live
credentials:

  - the temp file is 600 from the moment it is created
  - the backup is 600 even when the source was not
  - backups are pruned so they do not accumulate forever
  - the final file is 600
  - an interrupted write does not leave a stray temp file

Usage:
    python3 tools/test-env-writer-security.py
"""

import os
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from env_writer import set_values, _prune_backups  # noqa: E402

failures = []


def check(label, ok, detail=""):
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n          {detail}")
        failures.append(label)


def mode_of(path):
    return stat.S_IMODE(os.stat(path).st_mode)


print("=== env_writer security properties ===\n")

# --- 1. the temp file is 600 while it is being written ---
# The writer uses os.open(..., 0o600) + os.fdopen(), so neither
# builtins.open nor os.fdopen sees the temp file path. Watch
# os.open instead and check the mode argument AND the resulting file.
tmpdir = tempfile.mkdtemp()
target = os.path.join(tmpdir, "stream-meta.env")
with open(target, "w") as f:
    f.write("SECRET=value\n")
os.chmod(target, 0o600)

import os as _os
orig_osopen = _os.open
observed = {}


class Watcher:
    def __call__(self, path, flags, mode=0o777, *args, **kwargs):
        if isinstance(path, str) and path.endswith(".tmp"):
            observed["requested_mode"] = mode
        fd = orig_osopen(path, flags, mode, *args, **kwargs)
        if isinstance(path, str) and path.endswith(".tmp"):
            try:
                observed["actual_mode"] = stat.S_IMODE(_os.fstat(fd).st_mode)
            except OSError:
                pass
        return fd


_os.open = Watcher()
set_values(target, {"SECRET": "v2"}, make_backup=False)
_os.open = orig_osopen
check("temp file is created with mode 600",
      observed.get("requested_mode") == 0o600,
      f"requested {oct(observed.get('requested_mode', 0))}")
check("temp file actually is 600 on disk",
      observed.get("actual_mode") == 0o600,
      f"actual {oct(observed.get('actual_mode', 0))}")

# --- 2. the backup is 600 even when the source was 644 ---
target2 = os.path.join(tmpdir, "second.env")
with open(target2, "w") as f:
    f.write("SECRET=value\n")
os.chmod(target2, 0o644)
set_values(target2, {"SECRET": "v2"}, make_backup=True)
backups = [f for f in os.listdir(tmpdir) if f.startswith("second.env.backup-")]
check("backup was created", len(backups) == 1, str(backups))
if backups:
    bm = mode_of(os.path.join(tmpdir, backups[0]))
    check("backup is 600 even when the source was 644", bm == 0o600,
          f"got {oct(bm)}")

# --- 3. backups are pruned ---
for i in range(8):
    set_values(target, {"SECRET": f"v{i}"}, make_backup=True)
backups = [f for f in os.listdir(tmpdir) if f.startswith("stream-meta.env.backup-")]
check("backups are pruned to the limit", len(backups) <= 5,
      f"{len(backups)} backups remain")
check("the newest backup is kept",
      backups and backups[-1] == max(backups), str(backups))

# --- 4. the final file is 600 ---
check("final file is 600", mode_of(target) == 0o600,
      f"got {oct(mode_of(target))}")

# --- 5. no stray temp file ---
leftovers = [f for f in os.listdir(tmpdir) if f.endswith(".tmp")]
check("no stray .tmp file", not leftovers, str(leftovers))

# --- 6. a failed write leaves nothing behind ---
# Patch os.fdopen to blow up after the temp file has been created.
# That is the realistic failure point (disk full, permission change).
target3 = os.path.join(tmpdir, "boom.env")
with open(target3, "w") as f:
    f.write("SECRET=value\n")
os.chmod(target3, 0o600)

import os as _os
orig_fdopen = _os.fdopen


class Boom:
    def __call__(self, *args, **kwargs):
        raise OSError("simulated failure")


_os.fdopen = Boom()
raised = False
try:
    set_values(target3, {"SECRET": "v2"}, make_backup=False)
except OSError:
    raised = True
finally:
    _os.fdopen = orig_fdopen
check("a failed write raises", raised, "no exception")
leftovers = [f for f in os.listdir(tmpdir) if f.endswith(".tmp")]
check("a failed write leaves no .tmp file", not leftovers, str(leftovers))
check("the original file is intact",
      open(target3).read().strip() == "SECRET=value",
      open(target3).read())

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
