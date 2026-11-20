#!/usr/bin/env python3
"""Preview server for the streaming relay.

Serves the hls.js player page AND a small recording API:

    POST /record/<land|vert>   -> records a 10s clip from the relay's HLS output
    GET  /clips                 -> lists recent clips
    GET  /clips/<name>         -> downloads a clip

Recording happens server-side with ffmpeg reading the RELAY's HLS output, so
the clip contains exactly the bytes the relay is forwarding to platforms.
"""

import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELAY_DIR = HERE.parent.parent
CLIP_DIR = Path.home() / "Movies" / "Relay-Clips"
API = "http://127.0.0.1:9997"
RELAY_HLS = "http://127.0.0.1:8888"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8899

CLIP_DIR.mkdir(parents=True, exist_ok=True)

# base -> runtime path, resolved live from the relay API
_resolve_lock = threading.Lock()


def resolve_paths():
    try:
        import urllib.request

        with urllib.request.urlopen(f"{API}/v3/paths/list", timeout=5) as r:
            items = json.load(r).get("items") or []
    except Exception:
        return {}

    names = [it.get("name") for it in items if it.get("name")]
    out = {}
    for base in ("land", "vert"):
        if base in names:
            out[base] = base
        else:
            pref = sorted(
                (n for n in names if n.startswith(base + "/")),
                key=lambda n: (n.count("/"), n),
            )
            if pref:
                out[base] = pref[0]
    return out


def record(base, seconds=10):
    """Record `seconds` of the relay's HLS output for `base`. Returns (ok, msg)."""
    paths = resolve_paths()
    runtime_path = paths.get(base)
    if not runtime_path:
        return False, f"{base} is not publishing"

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = CLIP_DIR / f"{stamp}-{base}.mp4"
    src = f"{RELAY_HLS}/{runtime_path}/index.m3u8?cookieCheck=1"

    # launchd does NOT load the shell profile, so PATH may not include
    # Homebrew. Resolve ffmpeg to an absolute path.
    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if not os.path.exists(ffmpeg):
        return False, "ffmpeg not found"

    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-i", src, "-t", str(seconds),
        "-c", "copy", "-movflags", "+faststart", str(out),
    ]
    try:
        subprocess.run(cmd, timeout=seconds + 30, capture_output=True, check=True)
    except subprocess.TimeoutExpired:
        return False, "recording timed out"
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode(errors="replace").strip().splitlines()
        return False, err[-1] if err else "ffmpeg failed"

    if not out.exists() or out.stat().st_size == 0:
        return False, "no data recorded"
    return True, str(out)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("preview: " + (fmt % args) + "\n")

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        m = re.fullmatch(r"/record/(land|vert)", self.path.split("?")[0])
        if not m:
            self._json(404, {"error": "unknown endpoint"})
            return
        base = m.group(1)
        ok, msg = record(base, 10)
        self._json(200 if ok else 500, {"ok": ok, "message": msg, "base": base})

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/clips":
            clips = sorted(
                (p for p in CLIP_DIR.glob("*.mp4")),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:20]
            self._json(200, {
                "clips": [
                    {
                        "name": p.name,
                        "size": p.stat().st_size,
                        "mtime": p.stat().st_mtime,
                        "url": "/clips/" + p.name,
                    }
                    for p in clips
                ],
                "dir": str(CLIP_DIR),
            })
            return
        if path.startswith("/clips/"):
            name = os.path.basename(path)
            target = CLIP_DIR / name
            if not target.exists() or not name.endswith(".mp4"):
                self.send_error(404)
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'inline; filename="{name}"')
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"preview server on http://127.0.0.1:{PORT}/  (clips -> {CLIP_DIR})")
    server.serve_forever()
