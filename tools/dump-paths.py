import json
import sys

d = json.load(sys.stdin)
for it in (d.get("items") or []):
    name = it.get("name")
    ready = it.get("ready")
    online = it.get("online")
    src = it.get("source") or {}
    vids = []
    for t in (it.get("tracks2") or []):
        if not isinstance(t, dict):
            continue
        props = t.get("codecProps") or {}
        if props.get("width"):
            vids.append(f"{props.get('width')}x{props.get('height')}")
    codecs = ",".join(
        t.get("codec", "?") for t in (it.get("tracks2") or []) if isinstance(t, dict)
    )
    print(
        f"  {name:<16} ready={str(ready):<5} online={str(online):<5} "
        f"video={','.join(vids) or '-':<11} codecs={codecs or '-'}"
    )
