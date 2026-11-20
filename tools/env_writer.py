#!/usr/bin/env python3
"""Shared helpers for writing credentials into stream-meta.env.

WHY THIS EXISTS
---------------
The token helpers used to only PRINT the lines to add to stream-meta.env.
That meant a human had to copy-paste them, and it was easy to paste the
wrong value -- on 2026-11-19 an authorization CODE got pasted into
KICK_TOKEN instead of the access token, and the tool then used it as a
bearer token.

These helpers write the file directly, preserve everything else in it
(comments, ordering, quoting style), keep mode 600, and make a backup
first.
"""

import os
import shutil
import time

CONFIG = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "stream-meta.env")

# How many timestamped backups to keep. Every backup holds a full set
# of credentials, so they should not pile up forever.
MAX_BACKUPS = 5


def _prune_backups(path, keep=MAX_BACKUPS):
    """Delete the oldest backups, keeping the `keep` most recent.

    Returns the number of files removed.
    """
    d = os.path.dirname(path) or "."
    prefix = os.path.basename(path) + ".backup-"
    try:
        entries = [f for f in os.listdir(d) if f.startswith(prefix)]
    except OSError:
        return 0
    if len(entries) <= keep:
        return 0
    # The names sort chronologically (YYYYMMDD-HHMMSS).
    entries.sort()
    removed = 0
    for name in entries[:-keep]:
        try:
            os.unlink(os.path.join(d, name))
            removed += 1
        except OSError:
            pass
    return removed


def _read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return f.readlines()


def set_values(path, values, make_backup=True):
    """Set one or more KEY=VALUE pairs in an env-style file.

    - Existing keys are updated IN PLACE (keeping their position and the
      surrounding comments).
    - Missing keys are appended.
    - Everything else in the file is untouched.
    - A timestamped backup is written first.
    - The file keeps mode 600.

    Returns (ok, message).
    """
    if not values:
        return False, "nothing to write"

    lines = _read_lines(path)
    remaining = dict(values)
    out = []

    for line in lines:
        stripped = line.strip()
        matched = None
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                matched = key
        if matched is None:
            out.append(line)
        else:
            value = remaining.pop(matched)
            # Preserve the original quoting style if there was one.
            if "=" in line and line.split("=", 1)[1].strip().startswith('"'):
                out.append(f'{matched}="{value}"\n')
            else:
                out.append(f"{matched}={value}\n")

    # Anything left over is a new key.
    for key, value in remaining.items():
        out.append(f"{key}={value}\n")

    if make_backup and os.path.exists(path):
        backup = f"{path}.backup-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(path, backup)
        # copy2 preserves the SOURCE mode. If the source was ever 644
        # the backup -- which holds every credential -- would be
        # world-readable. Force 600 on it.
        os.chmod(backup, 0o600)
        _prune_backups(path, MAX_BACKUPS)

    tmp = f"{path}.tmp"
    # Create the temp file with 600 from the start. The default umask
    # would leave the credentials world-readable in the window between
    # the write and the replace below.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.writelines(out)
    except Exception:
        # Do not leave a stray temp file with credentials in it.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.replace(tmp, path)
    os.chmod(path, 0o600)

    # Verify by reading back. An empty value is a legitimate value (it
    # clears a key), so only a MISSING key counts as a failure.
    check = {}
    with open(path) as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                check[k.strip()] = v.strip().strip('"').strip("'")

    missing = [k for k in values if k not in check]
    if missing:
        return False, f"could not verify: {missing}"

    written = [k for k in values if check.get(k)]
    return True, f"wrote {len(written)} key(s) to {path}"
