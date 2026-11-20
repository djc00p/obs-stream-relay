import json
import sys

# Resolve the live runtime path names for the land and vert streams.
# Prints two space-separated names on one line (for shell read), or empty
# strings when a stream is not publishing.
items = json.load(sys.stdin).get("items") or []
names = [it.get("name") for it in items if it.get("name")]


def resolve(base):
    if base in names:
        return base
    prefixed = [n for n in names if n.startswith(base + "/")]
    if not prefixed:
        return ""
    prefixed.sort(key=lambda n: (n.count("/"), n))
    return prefixed[0]


print(f"{resolve('land')} {resolve('vert')}")
