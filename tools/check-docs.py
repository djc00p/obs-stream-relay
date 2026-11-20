#!/usr/bin/env python3
"""Verify the documentation matches the code.

Every command, file path, and tool referenced in docs/ and README.md
must actually exist in the repo. A doc that names a script that was
renamed is worse than no doc.

Usage:
    python3 tools/check-docs.py <repo-root>
"""

import os
import re
import sys

# Commands referenced in docs, as (doc-relative-path, script-name).
SCRIPT_REFS = [
    ("README.md", "scripts/go-live.sh"),
    ("README.md", "scripts/dry-run.sh"),
    ("README.md", "scripts/check-wiring.sh"),
    ("README.md", "scripts/relay.sh"),
    ("README.md", "scripts/refresh-keys.sh"),
    ("README.md", "scripts/record-clip.sh"),
    ("README.md", "scripts/test-relay.sh"),
    ("README.md", "tools/stream-meta.sh"),
    ("README.md", "tools/kick-token.sh"),
    ("README.md", "tools/twitch-token.sh"),
    ("README.md", "tools/youtube-token.sh"),
    ("README.md", "tools/platform-live.sh"),
    ("README.md", "tools/check-twitch-state.sh"),
    ("README.md", "tools/check-kick-state.sh"),
    ("README.md", "tools/check-youtube-redirect.sh"),
    ("README.md", "tools/yt-channel-id.sh"),
    ("docs/SETUP.md", "scripts/relay.sh"),
    ("docs/SETUP.md", "scripts/dry-run.sh"),
    ("docs/SETUP.md", "scripts/go-live.sh"),
    ("docs/SETUP.md", "scripts/check-wiring.sh"),
    ("docs/STREAM-META.md", "tools/stream-meta.sh"),
    ("docs/STREAM-META.md", "tools/kick-token.sh"),
    ("docs/STREAM-META.md", "tools/twitch-token.sh"),
    ("docs/STREAM-META.md", "tools/youtube-token.sh"),
    ("docs/STREAM-META.md", "tools/test-write-all.sh"),
    ("docs/STREAM-META.md", "tools/resolve-twitch-uid.sh"),
    ("docs/STREAM-META.md", "tools/check-twitch-state.sh"),
    ("docs/STREAM-META.md", "tools/check-kick-state.sh"),
    ("docs/STREAM-META.md", "tools/check-youtube-client.sh"),
    ("docs/STREAM-META.md", "tools/check-youtube-redirect.sh"),
    ("docs/STREAM-META.md", "tools/check-youtube-api-key.sh"),
    ("docs/TROUBLESHOOTING.md", "tools/platform-live.sh"),
    ("docs/TROUBLESHOOTING.md", "tools/rtmp-probe.sh"),
    ("docs/TROUBLESHOOTING.md", "tools/resolve-twitch-uid.sh"),
    ("docs/TROUBLESHOOTING.md", "tools/test-write-all.sh"),
    ("docs/TROUBLESHOOTING.md", "scripts/dry-run.sh"),
    ("docs/TROUBLESHOOTING.md", "scripts/check-wiring.sh"),
    ("docs/GET-KEYS.md", "scripts/dry-run.sh"),
    ("docs/GET-KEYS.md", "scripts/refresh-keys.sh"),
    ("docs/GET-KEYS.md", "scripts/relay.sh"),
    ("docs/PLATFORMS.md", "tools/resolve-twitch-uid.sh"),
    ("docs/PLATFORMS.md", "tools/find-kick-ingest.sh"),
    ("docs/PLATFORMS.md", "scripts/relay.sh"),
]

# Doc files that must exist.
REQUIRED_DOCS = [
    "README.md",
    "docs/SETUP.md",
    "docs/GET-KEYS.md",
    "docs/STREAM-META.md",
    "docs/TROUBLESHOOTING.md",
    "docs/ARCHITECTURE.md",
    "docs/PLATFORMS.md",
    "LICENSE",
    ".gitignore",
    "scripts/mediamtx.yml",
    "scripts/stream-keys.env.example",
    "scripts/stream-meta.env.example",
]

# Internal doc links -- each must resolve.
LINK_RE = re.compile(r"\]\(([^)#]+?\.md)(?:#[^)]*)?\)")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    failures = []

    def check(label, ok, detail=""):
        if ok:
            print(f"  PASS  {label}")
        else:
            print(f"  FAIL  {label}\n          {detail}")
            failures.append(label)

    print("=== documentation accuracy check ===\n")

    print("required files:")
    for rel in REQUIRED_DOCS:
        p = os.path.join(root, rel)
        check(rel, os.path.exists(p), f"missing: {p}")

    print("\nscripts referenced by docs:")
    for doc, script in SCRIPT_REFS:
        p = os.path.join(root, script)
        check(f"{doc} -> {script}", os.path.exists(p), f"missing: {p}")

    print("\ninternal doc links:")
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            docpath = os.path.join(dirpath, fn)
            docrel = os.path.relpath(docpath, root)
            with open(docpath) as f:
                text = f.read()
            for m in LINK_RE.finditer(text):
                target = m.group(1)
                if target.startswith("http"):
                    continue
                resolved = os.path.normpath(
                    os.path.join(os.path.dirname(docpath), target))
                if not os.path.exists(resolved):
                    check(f"{docrel} -> {target}", False,
                          f"broken link -> {resolved}")

    print("\nexecutables have a shebang:")
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, "scripts")):
        for fn in filenames:
            if not fn.endswith(".sh"):
                continue
            p = os.path.join(dirpath, fn)
            with open(p) as f:
                first = f.readline()
            check(f"scripts/{fn}", first.startswith("#!"),
                  "no shebang -- will not run directly")

    print("\nconfig examples are complete:")
    for name, required in [
        ("scripts/stream-keys.env.example",
         ["YT_LAND_KEY", "YT_VERT_KEY", "TWITCH_KEY", "KICK_KEY", "IG_KEY"]),
        ("scripts/stream-meta.env.example",
         ["TWITCH_CLIENT_ID", "TWITCH_TOKEN", "KICK_CLIENT_ID",
          "KICK_CLIENT_SECRET", "KICK_TOKEN", "YT_TOKEN", "YT_API_KEY"]),
    ]:
        p = os.path.join(root, name)
        if not os.path.exists(p):
            continue
        with open(p) as f:
            text = f.read()
        for key in required:
            check(f"{name} has {key}", key in text, "key not present")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
