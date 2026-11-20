# Platform Notes

Per-platform specifics: ingest URLs, key lifetimes, quirks, and settings that
have to be right before a stream will start.

---

## Ingest URLs

Verified working. These change rarely, but check if a platform suddenly
rejects a key you know is good.

| Platform | URL |
|---|---|
| YouTube | `rtmps://a.rtmps.youtube.com:443/live2` |
| Twitch | `rtmp://ingest.global-contribute.live-video.net/app` |
| Kick | `rtmps://fa723fc1b171.global-contribute.live-video.net/` |
| Instagram | `rtmps://edgetee-upload-den2-1.xx.fbcdn.net:443/rtmp/` |
| TikTok | `rtmps://live.tiktokcdn.com/live` |

Instagram and TikTok URLs come from the dashboard and change per session.
`stream-keys.env` has `IG_URL` and `TIKTOK_URL` entries for that.

Find Kick's current ingest host:

```bash
./tools/find-kick-ingest.sh
```

---

## YouTube

**Two channels, two keys.** One key per channel. Landscape and portrait need
separate channels — see [GET-KEYS.md](GET-KEYS.md#youtube--you-need-two-keys).

**Stream key format:** 24 characters, `xxxx-xxxx-xxxx-xxxx-xxxx`.

**Latency.** YouTube's RTMP ingest adds 3–8 seconds of latency. Expect the
preview to be behind the live signal.

**The `live` chat column.** In the YouTube Studio live control room, the
**Chat** column is for controlling a stream from the browser. Use the
**Stream key** field for RTMP ingest.

**Category.** A numeric id. `20` is Gaming. Look yours up:

```bash
./tools/stream-meta.sh --check
```

**Metadata needs OAuth.** The API key alone cannot change a title. See
[STREAM-META.md](STREAM-META.md#youtube).

---

## Twitch

**Stream key format:** 44 characters, `live_<user_id>_<token>`.

**Multistreaming must be enabled.** Stream Settings → **Enable
multistreaming**. Off by default. With it off, Twitch accepts the
handshake and refuses the publish — which looks exactly like a bad key.

**One broadcast per channel.** A second publish is refused. See
[TROUBLESHOOTING.md](TROUBLESHOOTING.md#the-live-channel-trap).

**The token needs the right scopes.** The metadata tools need
`channel:manage:broadcast`. The key checker needs
`channel:read:stream_key` — without it the API answers `401 Missing scope`.

**User id vs login.** `TWITCH_USER_ID` must be numeric:

```bash
./tools/resolve-twitch-uid.sh
```

---

## Kick

**Stream key format:** 56 characters, `sk_<region>_<token>`.

**Key lifetime.** Kick keys expire. Copy one right before you go live.

**One broadcast per channel**, same as Twitch.

**Channel writes need the channel in the body.** `PATCH
/public/v1/channels` requires `channel_slug`. Without it:
`400 Invalid request`.

**Writes only apply while live.** A `PATCH` to an offline channel returns
`204` and changes nothing.

**Categories are a fixed enum**, looked up by name:

```
GET /public/v1/categories?name=<name>
```

**Token scopes.** `channel:read`, `channel:write`, `user:read`.

**Refresh tokens last 30 days** on a sliding window. Access tokens last 2
hours.

---

## Instagram

**Session-scoped key.** ~1 hour. Get it right before you go live.

**Must be a Professional account** — Creator or Business. Personal accounts
cannot use the Live API.

**Two-factor authentication** is required for Professional accounts.

**The key is only valid after you click "Go Live"** in the Live Dashboard.
Copy it before that and you get a key that will not authenticate.

**Delivers at 720p.** Design the portrait canvas for 720p.

**The UI covers the bottom-right** of the frame. Keep anything important out
of that corner.

**Audio sample rate.** Instagram expects 44.1 kHz. OBS defaults to 48 kHz,
which can cause Instagram to drop the audio track. Set 44.1 kHz for the
portrait output.

**Server URL.** Instagram gives a URL with a query string
(`?s_bl=1&s_fbp=...`). The whole thing is the key. The base host is
`edgetee-upload-<region>-1.xx.fbcdn.net`.

---

## TikTok

**Session-scoped key.** ~1 hour.

**Switch to Software mode before copying the key.** Copying while in the
browser mode gives you the web ingest URL instead of the RTMP one.

**Optimise for:** should be **Software**.

**Requirements.** TikTok LIVE studio needs a follower count or an
invitation, depending on region.

**Rotating mid-stream** is supported and does not drop the stream:

```bash
./scripts/relay.sh add-forward vert "rtmps://live.tiktokcdn.com/live" "NEW_KEY"
```

---

## Aitum

Aitum is an OBS plugin that manages outputs. Three things to know.

### Close OBS before editing its config

Aitum writes its own configuration file and saves on exit. Editing it while
OBS is running means your changes get overwritten.

The config lives at:

```
~/Library/Application Support/obs-studio/basic/profiles/<profile>/aitum.json
```

### Nested encoders

An Aitum output contains a nested encoder. If the encoder's URL does not
match the output's destination, the two evict each other — the stream
flickers on a multi-second cycle.

### Aitum may add its own output

If you already have OBS publishing to `land`, an Aitum output pointing
elsewhere creates a third publisher. `check-wiring.sh` flags it.

See [docs/ARCHITECTURE.md](ARCHITECTURE.md) for the relay side.

---

## The vertical canvas plugin

This plugin adds its **own** output on top of whatever you configure. That
output publishes to a path like `vertical/land` — a third publisher that
nobody reads from.

**Fix it in the plugin's UI.** Plugins overwrite their config file on exit,
so editing the JSON does not stick.

Its config lives at:

```
~/Library/Application Support/obs-studio/plugin_config/vertical-canvas/config.json
```

Disable the file-level output, or point it somewhere the relay does not
forward.

---

## Key lifetimes at a glance

| Platform | Lifetime | Rotation needed |
|---|---|---|
| YouTube | Until you reset it | No |
| Twitch | Until you reset it | No |
| Kick | Hours to a day | Occasionally |
| Instagram | ~1 hour, per session | Yes, every stream |
| TikTok | ~1 hour, per session | Yes, every stream |

---

## Platform-specific metadata support

| Platform | Title | Category |
|---|---|---|
| YouTube | ✅ | ✅ numeric id |
| Twitch | ✅ | ✅ category enum |
| Kick | ✅ | ✅ fixed enum |
| Instagram | ❌ | ❌ |
| TikTok | ❌ | ❌ |

See [STREAM-META.md](STREAM-META.md).
