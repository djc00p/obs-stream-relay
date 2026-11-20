import json
import sys

d = json.load(sys.stdin)
print(json.dumps(d, indent=2)[:4000])
