# Setup

Complete install and setup, step by step. Each step says what to do, how to
check you did it, and what to do when it does not work.

Estimated time: 30 minutes.

---

## Step 1 — Get the repo

```bash
git clone https://github.com/YOUR_ACCOUNT/obs-stream-relay.git
cd obs-stream-relay
```

**Check:** `ls` shows `scripts/`, `tools/`, `docs/`.

---

## Step 2 — Install the dependencies

```bash
brew install mediamtx
```

If you would rather not use Homebrew, download the binary into the repo
root:

```bash
curl -sSL https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_darwin_arm64.tar.gz \
  | tar xz mediamtx
chmod +x mediamtx
```

Check the other tools are present:

```bash
for t in bash python3 ffmpeg curl nc; do
  command -v "$t" >/dev/null && echo "✓ $t" || echo "✗ $t — MISSING"
done
```

**Check:** all five print `✓`.

**If `ffmpeg` is missing:** `brew install ffmpeg`. It is only needed by
`dry-run.sh`.

---

## Step 3 — Create the config files

The templates live in `scripts/`. The working copies live in the repository
root, because the scripts look for them there.

```bash
cp scripts/mediamtx.yml        mediamtx.yml
cp scripts/stream-keys.env.example stream-keys.env
cp scripts/stream-meta.env.example stream-meta.env
chmod 600 stream-keys.env stream-meta.env
```

**Check:**

```bash
ls -l stream-keys.env stream-meta.env
```

Both should show `-rw-------` (mode 600).

---

## Step 4 — Collect your stream keys

You need one stream key per platform. The keys live in each platform's
dashboard, and every platform has a slightly different process.

Full instructions with screenshots-to-be:
**[docs/GET-KEYS.md](GET-KEYS.md)**.

Quick version:

| Platform | Where the key is | Shape |
|---|---|---|
| YouTube (landscape) | Studio → Stream → Stream key | 24 chars, `xxxx-xxxx-xxxx-xxxx-xxxx` |
| YouTube (portrait) | A second YouTube channel, same page | 24 chars |
| Twitch | Creator Dashboard → Stream Key | 44 chars, `live_<id>_<token>` |
| Kick | Channel → Stream Settings → Stream Key | 56 chars, `sk_<region>_<token>` |
| Instagram | Live Dashboard → Stream Key | 124 chars, session-scoped |
| TikTok | LIVE studio → Stream key | session-scoped |

Put them in `stream-keys.env`:

```bash
YT_LAND_KEY=xxxx-xxxx-xxxx-xxxx-xxxx
YT_VERT_KEY=xxxx-xxxx-xxxx-xxxx-xxxx
TWITCH_KEY=live_00000000_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
KICK_KEY=sk_us-west-2_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
IG_KEY=1193042257001228?s_bl=1&s_fbp=dfw5-3&...
```

**Check:**

```bash
./scripts/dry-run.sh
```

Section 2 checks that each key is present and has the right shape. It does
not connect to anything yet.

---

## Step 5 — Start the relay

```bash
./scripts/relay.sh start
```

**Check:**

```bash
./scripts/relay.sh status
```

You should see the server running and the two paths configured.

**If it says the relay is not running**, look at `mediamtx.log` in the repo
root.

---

## Step 6 — Configure OBS

You need **two outputs**. Both go to `localhost`. The stream key is ignored
by the relay — it only exists because OBS requires the field.

### Output 1 — landscape

| Setting | Value |
|---|---|
| Service | Custom / RTMP |
| Server | `rtmp://127.0.0.1:1935/land` |
| Stream Key | `land` |

### Output 2 — portrait

| Setting | Value |
|---|---|
| Service | Custom / RTMP |
| Server | `rtmp://127.0.0.1:1935/vert` |
| Stream Key | `vert` |

### If you use Aitum

Aitum is an OBS plugin that manages outputs. Two notes:

- Aitum writes its own configuration file. **Close OBS before editing that
  file by hand**, or Aitum will overwrite your changes when it next saves.
- Aitum may add its own output on top of yours. Two publishers on the same
  path evict each other every few seconds. After configuring Aitum, run
  `./scripts/check-wiring.sh` to see whether anything unexpected is
  publishing.

See [docs/PLATFORMS.md](PLATFORMS.md#aitum) for the details.

### If you use the vertical canvas plugin

That plugin adds its **own** output. Disable it, or give it a different
path. Otherwise you get a third publisher (`vertical/land`) that nobody is
reading from.

**Check:**

```bash
./scripts/check-wiring.sh
```

Every listed path should be one you expect.

---

## Step 7 — Dry run

```bash
./scripts/dry-run.sh --all
```

This opens each platform's RTMP endpoint, completes the handshake, and
closes the connection. **No video is published.**

Expected output:

```
  --- YouTube (landscape) ---
  ✓ YouTube (landscape) — a.rtmps.youtube.com:443 reachable
  ✓ YouTube (landscape) — handshake accepted, credential valid
```

**If a platform is rejected**, see
[docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md#platform-rejected-the-credentials).

One result is expected and not an error:

```
  ! Twitch — channel is ALREADY LIVE (a second publish is rejected)
```

That means the channel is already broadcasting. Twitch and Kick allow one
broadcast per channel, so the probe cannot connect a second time. It is
proof your forward is working, not proof of a problem.

---

## Step 8 — Go live

```bash
./scripts/go-live.sh
```

This prompts for each platform's key (or reads `stream-keys.env`), clears
stale targets, applies the new ones, and prints your OBS settings.

**Check:**

```bash
./scripts/check-wiring.sh
```

You should see each path and its forwards.

---

## Step 9 — Set your stream title and category

Optional. Requires OAuth tokens — see
[docs/STREAM-META.md](STREAM-META.md).

```bash
cd tools
./kick-token.sh       # opens a browser, writes the token to the config
./twitch-token.sh
./youtube-token.sh
cd ..
```

Then:

```bash
./tools/stream-meta.sh --title "My stream title" --game "Just Chatting"
```

---

## Step 10 — Set up the services (optional but recommended)

Running the relay and the preview player as launchd services means they
survive reboots.

### The relay

Create `~/Library/LaunchAgents/com.example.streaming-relay.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.example.streaming-relay</string>
  <key>ProgramArguments</key>
  <array>
    <string>/FULL/PATH/TO/obs-stream-relay/mediamtx</string>
    <string>/FULL/PATH/TO/obs-stream-relay/mediamtx.yml</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/FULL/PATH/TO/obs-stream-relay</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/FULL/PATH/TO/obs-stream-relay/mediamtx.log</string>
  <key>StandardErrorPath</key>
  <string>/FULL/PATH/TO/obs-stream-relay/mediamtx.err.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.example.streaming-relay.plist
```

Replace `com.example.streaming-relay` with your own reverse-DNS label, and
use the same label in the scripts' "start the relay" hints.

### The preview player

See [docs/ARCHITECTURE.md](ARCHITECTURE.md#the-preview-player).

---

## Where things are

```
obs-stream-relay/
├── scripts/          the shell scripts you run
│   ├── mediamtx.yml  the relay configuration
│   └── *.env.example config templates
├── tools/            python helpers + their .sh wrappers
├── docs/             the documentation
├── mediamtx.yml      your working copy of the relay config
├── stream-keys.env   your stream keys        (mode 600, gitignored)
└── stream-meta.env   your OAuth tokens       (mode 600, gitignored)
```

The working config files are at the repository root on purpose: the scripts
resolve paths relative to their own location, so the same layout works
whether you cloned into `$HOME/code/` or anywhere else.

---

## Next steps

- [docs/GET-KEYS.md](GET-KEYS.md) — every platform's key, in detail
- [docs/STREAM-META.md](STREAM-META.md) — titles and categories
- [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) — when something breaks
- [docs/PLATFORMS.md](PLATFORMS.md) — per-platform quirks and key lifetimes
