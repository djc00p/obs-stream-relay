# Getting Your Stream Keys

One stream key per platform. This document covers where each key comes from,
what shape it has, and when it expires.

| Platform | Where | Shape | Lifetime |
|---|---|---|---|
| YouTube (landscape) | Studio → Stream | `xxxx-xxxx-xxxx-xxxx-xxxx` (24) | Until you reset it |
| YouTube (portrait) | Second channel, Studio → Stream | `xxxx-xxxx-xxxx-xxxx-xxxx` (24) | Until you reset it |
| Twitch | Creator Dashboard → Stream Key | `live_<id>_<token>` (44) | Until you reset it |
| Kick | Channel → Stream Settings | `sk_<region>_<token>` (56) | Hours to a day |
| Instagram | Live Dashboard → Stream Key | 124 chars | ~1 hour, single session |
| TikTok | LIVE studio → Stream key | varies | ~1 hour, single session |

**Kick, Instagram, and TikTok keys expire.** Copy them right before you go
live. The other three last until you reset them.

---

## YouTube — you need TWO keys

YouTube gives one key per **channel**, not per output. To send landscape and
portrait to two different places you need two channels.

### Getting a key

1. Open <https://studio.youtube.com>
2. **Create** → **Go live** → **Stream**
3. The **Stream key** is at the bottom of the dialog
4. **Copy**

The key only appears while that dialog is open, and only while you are
actually set to stream. Close the dialog and it is gone from view (it is
still there if you reopen it).

### Getting a SECOND key

1. In YouTube Studio, click your profile picture → **Add or manage a
   channel** → **Create channel**
2. Name it (for example "Portrait")
3. Switch to that channel
4. **Create** → **Go live** → **Stream**
5. Copy the **Stream key**

You now have two keys, one per channel. Both are `xxxx-xxxx-xxxx-xxxx-xxxx`.

### Note

YouTube's live control room also has a **Chat** column. That is for
controlling a stream from the browser, not for RTMP ingest. Use the
**Stream key** field.

---

## Twitch

1. Open <https://dashboard.twitch.tv/settings/stream>
2. Under **Stream Key**, **Show**
3. **Copy**

Shape: `live_<user_id>_<token>`, 44 characters total.

### Multi-streaming on Twitch

Twitch's **multistreaming** toggle must be **on** for you to send RTMP
ingest to a channel. It is off by default.

> Stream Settings → **Enable multistreaming**

With it off, Twitch accepts the connection during a handshake and then
refuses the publish.

---

## Kick

1. Open your channel on <https://kick.com>
2. **Channel Settings** (or the creator dashboard)
3. **Stream Settings**
4. **Stream Key** → **Copy**

Shape: `sk_<region>_<token>`, 56 characters total. The region looks like
`sk_us-west-2_`.

### Kick's multistream toggle

Kick also has a multistream setting that must be enabled. It is on by
default for new channels, but check it if the handshake is refused.

---

## Instagram

Instagram's key is **session-scoped** and short-lived. Get it right before
you go live.

1. Open <https://www.instagram.com> → **Go live** (or the Live Dashboard)
2. Set a title, pick the audience
3. Pick the **Software** option (not "Stream to Instagram" from the phone)
4. Copy **both** the **Server URL** and the **Stream key**
5. **Click "Go Live"** — the key only becomes valid once you do

The stream key is 124 characters and includes a query string.

### Requirements

- Your Instagram account must be set to **Professional** (Creator or
  Business), not Personal.
- You need to be **at least 16**, or have a parent/guardian's account
  linked.
- Two-factor authentication must be enabled for Professional accounts.

### Instagram delivers at 720p

This matters if your portrait canvas is designed for 1080p. Instagram
transcodes to 720p, so your vertical output will be softer than it looks in
the preview. Design the vertical canvas for 720p if you care about the
final quality.

### Instagram's UI covers the bottom-right

The Instagram live interface overlays the bottom-right corner of the
frame. Keep anything important (your face, a watermark, a logo) out of
that corner.

### The audio sample rate gotcha

Instagram expects **44.1 kHz** audio. OBS defaults to 48 kHz, which is
fine everywhere else. Instagram occasionally drops the audio track when the
sample rate does not match what it expects.

Set the OBS audio sample rate to 44.1 kHz, or set it just for the portrait
output.

---

## TikTok

Same shape as Instagram: session-scoped, right before you go live.

1. Open <https://www.tiktok.com/live/studio>
2. Set up the stream (title, category)
3. **Go live** → **Stream** → **Use software**
4. Copy the **Server URL** and the **Stream key**

### The order matters

This trips people up:

1. Set up the stream in LIVE studio
2. **Switch "Set up your stream" to "Software"**
3. Copy the server URL and key
4. **Only then** connect OBS

If you copy the key before switching to Software, you get the *web* ingest
URL instead of the RTMP one.

### Two settings to change

- **Optimise for:** — set to **Software** if you are using OBS
- **Resolution / bitrate** — TikTok's recommended values are in the studio

### Rotating the key mid-stream

TikTok's key expires in about an hour. You can rotate it without dropping
the stream:

```bash
./scripts/relay.sh add-forward vert "rtmps://live.tiktokcdn.com/live" "NEW_KEY"
```

The same URL means the key is **replaced in place**. The stream does not
restart and OBS stays connected.

---

## Putting the keys in

Edit `stream-keys.env`:

```bash
YT_LAND_KEY="xxxx-xxxx-xxxx-xxxx-xxxx"
YT_VERT_KEY="xxxx-xxxx-xxxx-xxxx-xxxx"
TWITCH_KEY="live_<user_id>_<token>"
KICK_KEY="sk_<region>_<token>"
IG_KEY="1193042257001228?s_bl=1&s_fbp=dfw5-3&..."
```

**Always quote the values.** The scripts source this file with `.`, so
the values are parsed as shell. An Instagram key contains `&`
characters, and an unquoted `&` backgrounds the command and silently
drops the variable — which looks like a *missing* key rather than a
quoting bug.

Keep the file at mode `600`:

```bash
chmod 600 stream-keys.env
```

Then check:

```bash
./scripts/dry-run.sh
```

Section 2 of the output verifies each key is present and correctly shaped.
Section 3 connects to each platform without publishing anything.

---

## Rotating an expired key

For Instagram and TikTok, use the wizard:

```bash
./scripts/refresh-keys.sh
```

Or do it by hand:

```bash
./scripts/relay.sh add-forward vert "rtmps://live.tiktokcdn.com/live" "NEW_KEY"
./scripts/relay.sh add-forward vert "rtmps://live.instagram.com/rtmp" "NEW_KEY"
```

**The URL must match exactly.** A different URL adds a second forward
instead of replacing the first, and you end up with two targets where one
should be. `check-wiring.sh` flags that.

---

## Security

- `stream-keys.env` holds live credentials. Mode `600`, never committed.
- A stream key is equivalent to "anyone can stream to your channel". Treat
  a leaked key like a leaked password.
- Reset your YouTube and Twitch keys if you ever paste them somewhere
  public. Both platforms make that a single click.
