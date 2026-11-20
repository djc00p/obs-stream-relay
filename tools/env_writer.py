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

CONFIG = os.path.expanduser("~/Streaming-Relay/stream-meta.env")


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

    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        f.writelines(out)
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
