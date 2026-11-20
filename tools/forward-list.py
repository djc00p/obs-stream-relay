import json
import sys

d = json.load(sys.stdin)
fwd = d.get("forward") or []
if len(sys.argv) > 1 and sys.argv[1] == "count":
    print(len(fwd))
else:
    for f in fwd:
        dest = f.get("dest") or ""
        url, _, frag = dest.partition("#")
        print(f"{url}\t{frag}")
