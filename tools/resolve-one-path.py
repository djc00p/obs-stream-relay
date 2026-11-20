import json
import sys

# Resolve one live runtime path name by base (e.g. "land" -> "land/land").
# Prints the path name, or nothing when that stream is not publishing.
base = sys.argv[1] if len(sys.argv) > 1 else ""
items = json.load(sys.stdin).get("items") or []
names = [it.get("name") for it in items if it.get("name")]

if base in names:
    print(base)
else:
    prefixed = sorted(
        (n for n in names if n.startswith(base + "/")),
        key=lambda n: (n.count("/"), n),
    )
    if prefixed:
        print(prefixed[0])
