#!/usr/bin/env python3
"""Self-test for env_writer.set_values.

This is the code that actually MUTATES stream-meta.env, so it gets the
most careful testing. It must:
  - update a key in place, keeping its position
  - keep comments, blank lines, and unrelated keys untouched
  - preserve the original quoting style
  - append keys that don't exist yet
  - keep mode 600
  - make a backup
  - allow clearing a value (empty string)
  - leave NO temp file behind

Usage:
    python3 tools/test-env-writer.py
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from env_writer import set_values

failures = []


def check(label, ok, detail=""):
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n          {detail}")
        failures.append(label)


ORIGINAL = """# Stream metadata credentials
# ----------------------------

# --- Twitch ---
TWITCH_CLIENT_ID=abc123
TWITCH_TOKEN=oldtoken

# --- Kick ---
KICK_TOKEN=oldkick
KICK_REFRESH_TOKEN="oldrefresh"
KICK_CHANNEL_SLUG=YOUR_HANDLE

# --- Defaults ---
STREAM_TITLE=
"""

tmpdir = tempfile.mkdtemp()
cfg = os.path.join(tmpdir, "stream-meta.env")
with open(cfg, "w") as f:
    f.write(ORIGINAL)
os.chmod(cfg, 0o600)

print("=== env_writer.set_values self-test ===\n")

# 1. Update existing keys.
ok, msg = set_values(cfg, {"TWITCH_TOKEN": "newtoken",
                            "KICK_TOKEN": "newkick"}, make_backup=False)
after = open(cfg).read()
check("reports success", ok, msg)
check("twitch token updated", "TWITCH_TOKEN=newtoken" in after, after)
check("kick token updated", "KICK_TOKEN=newkick" in after, after)

# 2. Structure preserved.
check("header comment kept", "# Stream metadata credentials" in after)
check("section comment kept", "# --- Kick ---" in after)
check("twitch client id untouched", "TWITCH_CLIENT_ID=abc123" in after)
check("slug untouched", "KICK_CHANNEL_SLUG=YOUR_HANDLE" in after)
check("blank lines kept", after.count("\n\n") == ORIGINAL.count("\n\n"))
check("line count unchanged", len(after.splitlines()) == len(ORIGINAL.splitlines()),
      f"{len(after.splitlines())} vs {len(ORIGINAL.splitlines())}")

# 3. Quoting style preserved for the key that had quotes.
check("quoted key keeps its quotes", 'KICK_REFRESH_TOKEN="oldrefresh"' in after, after)
# ...and an unquoted key stays unquoted.
check("unquoted key stays unquoted", "\nTWITCH_TOKEN=newtoken\n" in after, after)

# 4. Order preserved.
check("twitch still before kick",
      after.index("TWITCH_TOKEN") < after.index("KICK_TOKEN"))

# 5. New key appended.
ok, msg = set_values(cfg, {"BRAND_NEW": "value123"}, make_backup=False)
after2 = open(cfg).read()
check("new key appended", "BRAND_NEW=value123" in after2, after2)
check("appended at the end",
      after2.rstrip().endswith("BRAND_NEW=value123"), after2[-100:])

# 6. Clearing a value works (empty string is a valid value).
ok, msg = set_values(cfg, {"KICK_TOKEN": ""}, make_backup=False)
after3 = open(cfg).read()
check("clearing reports success", ok, msg)
check("value cleared", "KICK_TOKEN=\n" in after3, after3)

# 7. Mode stays 600.
mode = stat.S_IMODE(os.stat(cfg).st_mode)
check("mode stays 600", mode == 0o600, f"got {oct(mode)}")

# 8. Backup made.
before = set(os.listdir(tmpdir))
set_values(cfg, {"TWITCH_TOKEN": "backuptest"}, make_backup=True)
after_files = set(os.listdir(tmpdir))
backups = [f for f in after_files - before if ".backup-" in f]
check("backup created", len(backups) == 1, str(backups))
if backups:
    bk = open(os.path.join(tmpdir, backups[0])).read()
    check("backup has the OLD value", "TWITCH_TOKEN=newtoken" in bk, bk[:200])

# 9. No temp file left behind.
leftovers = [f for f in os.listdir(tmpdir) if f.endswith(".tmp")]
check("no temp file left", not leftovers, str(leftovers))

# 10. The result is still a valid shell env file.
rc = subprocess.run(
    ["bash", "-c",
     f'. "{cfg}" && [ "$KICK_TOKEN" = "" ] && [ "$TWITCH_CLIENT_ID" = "abc123" ]'],
    capture_output=True, text=True)
check("still sources correctly in bash", rc.returncode == 0,
      f"rc={rc.returncode} {rc.stderr[:200]}")

shutil.rmtree(tmpdir)

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
