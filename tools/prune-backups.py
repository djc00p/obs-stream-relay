#!/usr/bin/env python3
"""Prune the accumulated credential backups in the live relay dir.

Every token helper run creates a timestamped backup of stream-meta.env.
Each backup holds a full set of live credentials. Keep the newest few,
delete the rest.

Usage:
    python3 tools/prune-backups.py <path> [--keep N]
"""

import os
import sys


def main():
    if len(sys.argv) < 2:
        print("usage: prune-backups.py <file> [--keep N]")
        return 2

    path = sys.argv[1]
    keep = 5
    if "--keep" in sys.argv:
        keep = int(sys.argv[sys.argv.index("--keep") + 1])

    d = os.path.dirname(path) or "."
    prefix = os.path.basename(path) + ".backup-"

    try:
        entries = sorted(f for f in os.listdir(d) if f.startswith(prefix))
    except OSError as e:
        print(f"error: {e}")
        return 1

    if len(entries) <= keep:
        print(f"  {len(entries)} backup(s), nothing to prune (keep {keep})")
        return 0

    removed = 0
    for name in entries[:-keep]:
        p = os.path.join(d, name)
        try:
            os.chmod(p, 0o600)
            os.unlink(p)
            removed += 1
            print(f"  removed {name}")
        except OSError as e:
            print(f"  could not remove {name}: {e}")

    print(f"  {removed} removed, {keep} kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
