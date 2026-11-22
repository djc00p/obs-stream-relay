# Troubleshooting

Every error this project produces, what actually causes it, and what to do.

Start here:

```bash
./scripts/dry-run.sh --all
```

It tells you which credential failed and why, instead of a generic
"something went wrong". This document explains what each message means.

---

## "Platform rejected the credentials"

```
✗ YouTube (landscape) — REJECTED by platform (credential or account issue)
```

A generic RTMP rejection. **Do not assume the key is wrong** — see
[the live-channel trap](#the-live-channel-trap) first, it is far more
common.

Then work down this list:

1. **Is the channel already live?** → `./tools/platform-live.sh twitch`
2. **Is the key stale?** Instagram, TikTok, and Kick keys expire.
   Copy a fresh one from the dashboard.
3. **Is the key the right shape?** `dry-run.sh` section 2 checks this.
4. **Is the account type allowed?** Some platforms refuse RTMP ingest on
   accounts that have not completed setup.

---

## The live-channel trap

```
✗ Twitch — REJECTED by platform (credential or account issue)
    [tls @ 0x...] IO error: End of file
```

**This is the most common false alarm.** Both Twitch and Kick allow exactly
**one** broadcast per channel. A second publish to a live channel is
refused, and `ffmpeg` reports it as a generic I/O error — indistinguishable
from a bad key.

Twitch refuses with `Input/output error`. Kick refuses by closing the TLS
connection, which looks like a network fault.

Check:

```bash
./tools/platform-live.sh twitch
./tools/platform-live.sh kick
```

`live` means the channel is already broadcasting and the rejection is
expected.

`dry-run.sh` now does this check for you and reports:

```
! Twitch — channel is ALREADY LIVE (a second publish is rejected)
```

and the summary says **All checks passed**.

---

## "Relay is not running"

```
✗ relay is NOT running — start with: launchctl kickstart -k gui/$(id -u)/com.example.streaming-relay
```

Start it:

```bash
./scripts/relay.sh start
```

Or check what is actually happening:

```bash
./scripts/relay.sh status
tail -30 mediamtx.log
```

---

## "Nothing shows up" after `go-live.sh`

Three possible causes, in order of likelihood.

### 1. OBS is publishing to the wrong path

The relay accepts `land` and `vert`. If OBS points somewhere else, nothing
arrives.

```bash
./scripts/check-wiring.sh
```

### 2. A stale publisher is evicting yours

If two publishers connect to the same path, they take turns — each one
evicts the other every few seconds. You see a stream flicker or nothing at
all.

`check-wiring.sh` flags unexpected paths. A path like `vertical/land` means
the vertical canvas plugin added its own output.

### 3. The forwards were applied to the wrong path

`go-live.sh` applies forwards to the path *names* configured in
`mediamtx.yml`. If you changed a path name, the forwards follow the new
name.

---

## The preview player shows nothing

**Open the player, not the raw playlist.** <http://127.0.0.1:8899/>

Two things bite people here.

### The runtime path is `land/land`, not `land`

The relay path is `land`, but the publisher appends a stream key as a path
segment. So the runtime path is `land/land`.

Resolve the live names:

```bash
./tools/preview-urls.sh
```

### `?cookieCheck=1` is required over plain http

MediaMTX sets a `Secure; HttpOnly` cookie. Browsers refuse to store a
`Secure` cookie over `http://`, so a bare playlist URL redirects back to
itself and answers `{"error":"no stream is available on path '...'"}` —
even when the stream is live.

Raw playlist URLs for VLC, ffplay, or scripted checks:

```
http://127.0.0.1:8888/land/land/index.m3u8?cookieCheck=1
http://127.0.0.1:8888/vert/vert/index.m3u8?cookieCheck=1
```

```bash
ffplay -i "http://127.0.0.1:8888/vert/vert/index.m3u8?cookieCheck=1"
```

Safari will offer to *download* a bare `.m3u8` rather than play it. Use
the player URL.

---

## An unexpected publisher appears

```
! unexpected path: vertical/land
```

Something other than your OBS scene is publishing. Common culprits:

| Path | Cause |
|---|---|
| `vertical/land` | The vertical canvas plugin's own output |
| `land/land` | Correct — the landscape output |
| `vert/vert` | Correct — the portrait output |

Fix it in the plugin's UI, not by editing its config file. Plugins
overwrite their config on exit.

---

## The dry run reports a key with the wrong shape

```
✗ YouTube (landscape) — key shape WRONG for youtube
```

The key does not match the expected pattern for that platform:

| Platform | Pattern |
|---|---|
| YouTube | 24 chars, `xxxx-xxxx-xxxx-xxxx-xxxx` |
| Twitch | 44 chars, `live_<digits>_<token>` |
| Kick | 56 chars, `sk_<region>_<token>` |
| Instagram | 124 chars, session key |

Usually this means the key was truncated when pasted, or the wrong key was
copied.

---

## A platform is missing from the dry run

```
! no key set (KICK_KEY) — will be skipped
```

Add the key to `stream-keys.env`, or skip the platform on purpose:

```bash
./scripts/dry-run.sh --skip "TikTok,Instagram"
```

or in `stream-keys.env`:

```bash
SKIP_PLATFORMS="TikTok Instagram"
```

A skipped platform never disqualifies the run.

---

## The `403 Permission denied on the service` (YouTube API key)

A YouTube API key that is valid but refused for the YouTube Data API.

Distinguish the causes:

| Test | Result | Meaning |
|---|---|---|
| Same request with **no key** | Same 403 | The service is not enabled on the project |
| Same request with a **bogus key** | `400 API key not valid` | The key itself is fine |
| `liveBroadcasts` with no credentials | `401 missing credential` | The service is enabled and reachable |

Fix: **APIs & Services → Library → YouTube Data API v3 → Enable**.

Creating an API key does not enable the API. These are separate actions.

---

## `redirect_uri_mismatch` (YouTube OAuth)

```
Error 400: redirect_uri_mismatch
```

The redirect URI sent does not match the one registered on the OAuth
client, **exactly**. The scheme is part of the match — `http://localhost`
is not `https://localhost`.

Find out what is registered:

```bash
./tools/check-youtube-redirect.sh
```

The helper detects the registered URI at runtime and uses it, so this only
happens if you changed the client.

---

## "Access blocked: ... has not completed the Google verification process"

```
The app is currently being tested, and can only be accessed by
developer-approved testers.
```

A new OAuth client defaults to **publishing status = Testing**. Only
accounts on the test-user list can use it.

**Fix (2 minutes):** Google Cloud Console → your project → **APIs &
Services** → **OAuth consent screen** → **Test users** → **Add users** →
your Google account.

Do not chase production publishing for a personal tool. It requires a
verified domain, a public privacy policy, an app homepage, and a demo
video.

---

## A credential write returns `400 Invalid request` (Kick)

`PATCH /public/v1/channels` needs the channel identified in the body:

```json
{"channel_slug": "your-handle", "stream_title": "..."}
```

Without `channel_slug` the API cannot tell which channel to change.

---

## A credential write returns `204` but nothing changed

Kick accepts channel writes and applies them **only while the channel is
live**. An offline channel gets `204` and no change.

This is not a scope problem — a missing scope gives `401` or `403`.

Verify the write path while live:

```bash
./tools/test-write-all.sh
```

---

## Twitch: `broadcaster_id` must be numeric

```
The parameter "broadcaster_id" was malformed: value must be a numeric
```

`TWITCH_USER_ID` must be the numeric user id, not the login name.

```bash
./tools/resolve-twitch-uid.sh
```

---

## Twitch category lookup finds nothing

`GET /helix/games?name=...` does a narrower match than
`GET /helix/search/categories?query=...`. A category that exists can be
invisible to the first endpoint.

The tools use the search endpoint.

---

## YouTube: `Incompatible parameters specified in the request: broadcastStatus, mine`

`broadcastStatus` and `mine` are mutually exclusive. Use `mine=true`
alone and filter client-side.

---

## YouTube: `Id is required` / `Scheduled start time is required` on a write

A `PUT` **replaces** the resource. Sending only the changed field fails.
Read the existing resource, change the one field, send the whole thing
back.

---

## The 10-second clip endpoint fails under launchd

`launchd` does not load your shell profile, so it cannot find programs
installed by Homebrew, pyenv, or asdf.

Use the absolute path to the binary in the plist's `ProgramArguments`, for
example:

```
/opt/homebrew/bin/ffmpeg
```

not just `ffmpeg`.

---

## `curl` returns `http=000` but python works

In a sandboxed environment the egress proxy may block `curl` while a
helper that falls back to a direct connection succeeds.

Shell scripts in this project call external APIs through
`tools/proxy_http.py` rather than `curl` for exactly this reason. If you
add a script that talks to a platform API, use the same helper.

---

## Getting more detail

Any RTMP rejection can be probed directly:

```bash
./tools/rtmp-probe.sh "Twitch" "rtmp://ingest.global-contribute.live-video.net/app" "$TWITCH_KEY"
```

And with full protocol logging:

```bash
ffmpeg -hide_banner -loglevel trace \
  -f lavfi -i "color=c=black:s=320x240:d=0.3:r=5" \
  -c:v libx264 -preset ultrafast -t 0.3 \
  -f flv "rtmp://ingest.global-contribute.live-video.net/app/$TWITCH_KEY" 2>&1 \
  | grep -iE "rtmp|error|status"
```

The trace shows how far the handshake got. If it reaches "Sending publish
command" and then fails, the connect succeeded and the **publish** was
refused — that points at the channel already being live, not at a bad key.

---

## Still stuck

Run the full suite and read the output:

```bash
./scripts/dry-run.sh --all
./scripts/check-wiring.sh
cd tools && ./test-write-all.sh
```
