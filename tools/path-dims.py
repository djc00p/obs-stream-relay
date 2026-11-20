import json
import sys

# Report the video dimensions of a relay path.
#
# The runtime path name is NOT the same as the config pattern. Aitum builds its
# publish URL as server + "/" + stream_key, so an output with server
# rtmp://127.0.0.1:1935/land and key "land" lands on the runtime path
# "land/land". The config pattern is the regex "~^land(/.*)?$".
#
# So we match by PREFIX: "land" matches "land", "land/land", "land/anything".
# Exact match is tried first so a literal path always wins.
d = json.load(sys.stdin)
argv = sys.argv[1:]
name_only = False
if argv and argv[0] == "--name":
    name_only = True
    argv = argv[1:]
target = argv[0] if argv else None


def dims(it):
    for t in (it.get("tracks2") or []):
        if not isinstance(t, dict):
            continue
        props = t.get("codecProps") or {}
        if props.get("width"):
            return f"{props.get('width')}x{props.get('height')}"
    return ""


items = d.get("items") or []

if not target:
    for it in items:
        got = dims(it)
        if got:
            print(f"{it.get('name')}\t{got}")
    sys.exit(0)


def pick(matches):
    """Exact match wins; otherwise shallowest path, then alphabetical."""
    for it in matches:
        if it.get("name") == target:
            return it
    if not matches:
        return None
    matches.sort(key=lambda it: (it.get("name", "").count("/"), it.get("name", "")))
    return matches[0]


# 1. exact match
exact = pick([it for it in items if it.get("name") == target])
if exact is not None:
    got = dims(exact)
    if got:
        print(exact.get("name") if name_only else got)
        sys.exit(0)

# 2. prefix match (land -> land/land)
pfx = pick([it for it in items if it.get("name", "").startswith(target + "/")])
if pfx is not None:
    got = dims(pfx)
    if got:
        print(pfx.get("name") if name_only else got)
        sys.exit(0)

print("")
