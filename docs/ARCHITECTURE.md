# Architecture

How the pieces fit together.

```
┌──────────────────────────────────────────────────────────────────────┐
│  OBS Studio                                                           │
│    Output "landscape"  ──▶  rtmp://127.0.0.1:1935/land                │
│    Output "portrait"   ──▶  rtmp://127.0.0.1:1935/vert                │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  MediaMTX  (localhost:1935)                                          │
│                                                                      │
│    path  ~^land(/.*)?$   ──▶  YouTube landscape                      │
│                              Twitch                                 │
│                              Kick                                   │
│                                                                      │
│    path  ~^vert(/.*)?$   ──▶  YouTube portrait                      │
│                              Instagram                              │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                        platform ingest endpoints
```

---

## Why a relay at all

Streaming platforms do not speak to each other. One OBS output goes to one
URL. To reach five platforms you need five publishers, and running five
publishers from one OBS scene is where encoders drift and machines fall
over.

The relay inverts that: **OBS publishes once, to localhost.** The relay
forwards that one stream to N platforms. Adding a platform is a config
change, not a new encoder.

The second win is **key rotation**. Instagram and TikTok issue
session-scoped keys that expire every hour or so. Replacing the forward
target changes the destination without touching OBS or interrupting the
stream.

---

## Paths and forwards

`mediamtx.yml` defines two path patterns:

```yaml
paths:
  ~^land(/.*)?$:
  ~^vert(/.*)?$:
```

They are regexes. `land` and `land/anything` both match the first.

### The runtime path is `land/land`

This confuses everyone the first time.

OBS publishes to `rtmp://127.0.0.1:1935/land` with stream key `land`.
MediaMTX treats the path as `/<path>/<streamkey>`, so the runtime path
becomes **`land/land`**.

That is why the HLS URL is `http://127.0.0.1:8888/land/land/index.m3u8`
and not `.../land/index.m3u8`.

Resolve the live names with:

```bash
./tools/preview-urls.sh
```

### Forwards

A forward is a destination for a path:

```yaml
paths:
  ~^land(/.*)?$:
    forward:
      - dest: rtmps://a.rtmps.youtube.com:443/live2#<your-key>
      - dest: rtmp://ingest.global-contribute.live-video.net/app#<your-key>
```

MediaMTX appends everything after `#` to the destination URL. That is how
the stream key gets attached.

`go-live.sh` writes these at runtime through the MediaMTX API rather than
editing the YAML, so a key change does not require a restart.

---

## The scripts

| Script | Talks to | Purpose |
|---|---|---|
| `relay.sh` | MediaMTX API, process | Start/stop, add/remove forwards live |
| `go-live.sh` | MediaMTX API | Clear stale forwards, apply the current keys |
| `dry-run.sh` | Platform ingest endpoints | Validate credentials without publishing |
| `check-wiring.sh` | MediaMTX API | Show what is connected, flag surprises |
| `refresh-keys.sh` | Platform dashboards + API | Guided key rotation |
| `record-clip.sh` | MediaMTX recording API | Cut a clip |

### The MediaMTX API

```
GET  http://127.0.0.1:9997/v3/paths/list
GET  http://127.0.0.1:9997/v3/config/paths/list
GET  http://127.0.0.1:9997/v3/config/paths/get/<name>
PATCH http://127.0.0.1:9997/v3/config/paths/patch/<name>
```

`<name>` is the URL-encoded path pattern — `~^land(/.*)?$` becomes
`~%5Eland%28%2F.%2A%29%3F%24`.

---

## The preview player

MediaMTX serves HLS on `:8888`. A small local page (`tools/preview/`) plays
both outputs side by side on `:8899`.

```
http://127.0.0.1:8899/
```

It uses hls.js and appends `?cookieCheck=1` to every playlist request.

**Why the query parameter?** MediaMTX sets a `Secure; HttpOnly` cookie.
Browsers refuse to store a `Secure` cookie over plain `http://`, so a bare
playlist URL redirects back to itself and answers
`{"error":"no stream is available on path '...'"}` — even when the stream is
live and working.

---

## The metadata layer

Separate from the relay, on purpose.

**RTMP carries no title or category metadata.** The relay forwards video
and nothing else. The stream title travels over each platform's own API.

`tools/stream-meta.py` implements that layer:

```
platform API  ◀──  stream-meta.py  ◀──  stream-meta.env
```

Each platform needs a different credential:

- **YouTube** — OAuth token (to write) plus API key (to read)
- **Twitch** — OAuth token plus client id
- **Kick** — OAuth token

See [STREAM-META.md](STREAM-META.md).

---

## Ports

| Port | What |
|---|---|
| 1935 | RTMP ingest — OBS publishes here |
| 8888 | HLS output |
| 9997 | MediaMTX API |
| 8899 | Preview player |
| 8554 | RTSP (not used by default) |
| 8000, 8001 | Metrics, pprof |

---

## Configuration files

| File | Contains | Mode |
|---|---|---|
| `stream-keys.env` | Platform stream keys | 600 |
| `stream-meta.env` | OAuth tokens and client credentials | 600 |
| `mediamtx.yml` | Relay paths and static forwards | 644 |

Both `.env` files are gitignored. The writers that touch `stream-meta.env`
back it up first and preserve comments, key order, and mode.

---

## Design notes

### Forwards are applied at runtime, not in YAML

Editing `mediamtx.yml` requires a restart, which drops OBS's connection.
Going through the API means a key rotation is a running system that never
drops the stream.

### The dry run publishes no video

`dry-run.sh` opens each ingest endpoint with a 0.2-second black clip.
That completes the RTMP handshake, which is where the platform validates
the credential, and then closes the connection. No meaningful content is
published, but some platforms briefly show a broadcast that immediately
ends.

### Unexpected publishers are detected

Two publishers on one path evict each other every few seconds. That
presents as a flickering stream or no stream at all, with nothing in the
OBS log.

`check-wiring.sh` and `go-live.sh` both flag paths that are not `land*` or
`vert*` — a path like `vertical/land` means a plugin added its own output.

### Failures are loud

`go-live.sh` reads the MediaMTX API back after applying forwards and exits
with an error if neither path has any. A silent zero-forward run looks
exactly like a successful one until you notice nothing is streaming.

### The live-channel trap

Twitch and Kick allow one broadcast per channel. A second publish is
refused, and `ffmpeg` reports it as a generic I/O error — the same thing a
bad key produces.

So before blaming a credential, the tools ask the platform API whether the
channel is already live. See
[TROUBLESHOOTING.md](TROUBLESHOOTING.md#the-live-channel-trap).
