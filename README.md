# OBS Stream Relay

Run one OBS scene to many platforms at once — landscape and portrait side by
side — without paying for a distribution service.

A local [MediaMTX](https://github.com/bluenviron/mediamtx) instance sits
between OBS and the platforms. OBS publishes to `localhost`; the relay
forwards each path to the platform ingest URLs you configure. Swap a
platform's key whenever it expires without restarting the stream.

```
                         ┌──────────────────────────────┐
  OBS ──land──▶         │  MediaMTX (localhost:1935)   │
       └──vert──▶        │    land/  ──▶ YouTube        │
                         │                Twitch        │
                         │                Kick          │
                         │    vert/  ──▶ YouTube (vert) │
                         │                Instagram     │
                         └──────────────────────────────┘
```

## What it does

- **Two outputs from one OBS.** Landscape and portrait publish to different
  paths and reach different platform keys.
- **Live key rotation.** Instagram and TikTok issue session keys that
  expire. Replace the forward target in place; the stream does not drop.
- **A dry run that does not broadcast.** Validate every credential with a
  0.2-second handshake before you go live.
- **Stream metadata.** Set the title and category on YouTube, Twitch, and
  Kick from one command.
- **A local preview.** Watch both outputs side by side at
  `http://127.0.0.1:8899/`.

## What it does not do

- It does not touch your OBS configuration. You add two outputs yourself.
- It does not transcode. Both outputs are whatever OBS sends.
- It does not manage your platform accounts or create API apps for you.
  The docs say how; the scripts do the OAuth dance after you register.

## Requirements

| | |
|---|---|
| OS | macOS (launchd is used for the services) |
| Runtime | OBS Studio, MediaMTX |
| Tools | `bash`, `python3`, `ffmpeg`, `curl`, `nc` |
| Python deps | none — the scripts use the standard library only |

`ffmpeg` is only used by the dry run to probe credentials.

## Install

```bash
git clone https://github.com/YOUR_ACCOUNT/obs-stream-relay.git
cd obs-stream-relay
```

Copy the config template and edit it:

```bash
cp scripts/mediamtx.yml mediamtx.yml
cp scripts/stream-keys.env.example stream-keys.env
cp scripts/stream-meta.env.example stream-meta.env
chmod 600 stream-keys.env stream-meta.env
```

The example files live in `scripts/` so the tree stays tidy; the working
copies live at the repository root because the scripts expect them there.

## Install MediaMTX

```bash
brew install mediamtx
```

Or download the release binary for your platform and put it in the repo
root:

```bash
curl -sSL https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_darwin_arm64.tar.gz \
  | tar xz mediamtx
```

## Setup

The full walkthrough is in **[docs/SETUP.md](docs/SETUP.md)**. The short
version:

1. **Get a stream key** from each platform. See
   [docs/GET-KEYS.md](docs/GET-KEYS.md).
2. **Put the keys** in `stream-keys.env`.
3. **Start the relay:** `./scripts/relay.sh start`
4. **Add two outputs to OBS** pointing at `rtmp://127.0.0.1:1935/land` and
   `rtmp://127.0.0.1:1935/vert`. Any stream key — it is ignored.
5. **Dry run:** `./scripts/dry-run.sh --all`
6. **Go live:** `./scripts/go-live.sh`

## Daily use

```bash
./scripts/go-live.sh     # apply the forwards
./scripts/check-wiring.sh  # what is connected right now
./scripts/relay.sh status  # relay status
```

## Scripts

| Script | What it does |
|---|---|
| `scripts/go-live.sh` | Prompts for keys, clears stale targets, applies forwards |
| `scripts/dry-run.sh` | Validates every credential without broadcasting |
| `scripts/check-wiring.sh` | Shows the live path list and flags surprises |
| `scripts/relay.sh` | Start/stop the relay, add/remove forwards at runtime |
| `scripts/refresh-keys.sh` | Guided wizard for rotating expired keys |
| `scripts/record-clip.sh` | Cut a clip out of the relay's recordings |
| `scripts/test-relay.sh` | End-to-end relay test with a synthetic stream |

## Tools

Python helpers the scripts call. Most have a `.sh` wrapper — use the
wrapper, it finds its own dependencies.

### Streaming metadata

| Tool | What it does |
|---|---|
| `tools/stream-meta.sh` | Set the stream title and category across platforms |
| `tools/platform-live.sh` | Report whether a channel is currently broadcasting |
| `tools/show-yt-broadcasts.sh` | List the broadcasts on the channel so you can see which one is live |

### OAuth and credentials

| Tool | What it does |
|---|---|
| `tools/twitch-token.sh` | Get and save a Twitch OAuth token |
| `tools/kick-token.sh` | Get and save a Kick OAuth token |
| `tools/youtube-token.sh` | Get and save a YouTube OAuth token |
| `tools/check-twitch-state.sh` | What the Twitch token actually has, and is the channel live |
| `tools/check-kick-state.sh` | Is the Kick channel live |
| `tools/check-twitch-key.sh` | Validate the Twitch stream key against the Twitch API |
| `tools/check-youtube-client.sh` | Check the OAuth client against Google |
| `tools/check-youtube-api-key.sh` | Verify the API key works and resolves the channel |
| `tools/check-youtube-redirect.sh` | Which redirect URI is registered on the OAuth client |
| `tools/resolve-twitch-uid.sh` | Resolve the Twitch numeric broadcaster id and save it |
| `tools/yt-channel-id.sh` | Resolve a handle to a `UC...` channel id |

The token helpers **write the config file themselves**. Do not copy a
token by hand — printing a value for a human to paste is how an
authorization code ends up where an access token belongs, and the two
look the same.

### Diagnostics and verification

| Tool | What it does |
|---|---|
| `tools/check-docs.sh` | Every command and internal link in the docs resolves |
| `tools/run-scan-for-pii.sh` | Scan a tree for names, handles, ids, paths, and credential shapes |
| `tools/check-unexpected-paths.sh` | Find relay paths that should not exist |
| `tools/live-paths.sh` | Dump the relay's live path state |
| `tools/list-cfg-paths.sh` | List the configured path patterns and their forward counts |
| `tools/find-kick-ingest.sh` | Discover the working Kick RTMPS ingest URL |
| `tools/probe-path.sh` | Publish a synthetic stream to a relay path and report what it does |
| `tools/inspect-live.sh` | Publish a synthetic stream, dump the raw API state, stop |
| `tools/verify-forward.sh` | Verify a forward target actually delivers |
| `tools/rtmp-probe.sh` | Probe one platform's RTMP ingest and show the real rejection reason |
| `tools/test-write-all.sh` | End-to-end write test for every platform, using the real code |
| `tools/test-yt-write.sh` | Pick the most recent broadcast |
| `tools/verify-youtube-oauth.sh` | End-to-end check of the YouTube OAuth path |
| `tools/verify-kick-token-path.sh` | End-to-end check of the Kick token exchange path |
| `tools/debug-twitch-token.sh` | Feed a fake redirect URL to the Twitch helper and show the output |
| `tools/debug-kick-token.sh` | Feed a fake redirect URL to the Kick helper and show the output |

### The preview player

| Tool | What it does |
|---|---|
| `tools/preview-server.sh` | Serve a local preview page for the two streams |
| `tools/preview-urls.sh` | Print the correct HLS preview URL, resolving the live path |
| `tools/preview-build.sh` | Build the preview page's static assets |
| `tools/preview-refresh.sh` | Refresh the preview page's path list from the live relay |

The preview runs on `127.0.0.1:8899` and shows both streams side by
side with their live dimensions.

### Internals

| Tool | What it does |
|---|---|
| `tools/load-env.sh` | Parse an env file as data — without executing it |
| `tools/env_writer.py` | The one writer for credential files (mode 600, atomic) |
| `tools/value_guard.py` | Refuse values that look like the wrong kind of credential |
| `tools/proxy_http.py` | The HTTP helper the python tools share |
| `tools/unexpected-paths.py` | Detect relay paths that should not exist |
| `tools/resolve-one-path.py` | Resolve one path's live state |
| `tools/forward-list.py` | List a path's forward targets |
| `tools/path-dims.py` | Report a path's video dimensions |

### Tests

Each test runs standalone and exits non-zero on failure.

```bash
for t in tools/run-test-*.sh tools/run-value-guard.sh; do bash "$t"; done
```

| Test | What it proves |
|---|---|
| `tools/run-test-env-writer.sh` | The credential writer updates in place and preserves the file |
| `tools/run-test-env-writer-security.sh` | Permissions, backup pruning, and cleanup on failure |
| `tools/run-test-load-env.sh` | The env file is not executed and values are not expanded |
| `tools/run-test-oauth-state.sh` | Every OAuth helper rejects a mismatched **and** a missing `state` |
| `tools/run-test-twitch-token.sh` | The Twitch helper parses redirects correctly |
| `tools/run-test-kick-token.sh` | The Kick helper parses redirects correctly |
| `tools/run-test-unexpected-paths.sh` | The unexpected-path detector works |
| `tools/run-value-guard.sh` | Wrong-shaped credentials are refused with a clear message |

## Docs

| Document | Covers |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Complete install and setup, step by step |
| [docs/GET-KEYS.md](docs/GET-KEYS.md) | Where to get every platform's stream key |
| [docs/STREAM-META.md](docs/STREAM-META.md) | Setting title and category |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Every error and what causes it |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the pieces fit together |
| [docs/PLATFORMS.md](docs/PLATFORMS.md) | Per-platform notes, key lifetimes, quirks |

## Security

- `stream-keys.env` and `stream-meta.env` hold live credentials. Keep them
  at mode `600` and never commit them. `.gitignore` already excludes them.
- The token helpers **write the config files themselves**. Do not copy and
  paste credential values by hand — an OAuth authorization code and an
  access token look nearly identical, and pasting the wrong one produces a
  confusing 401.
- `dry-run.sh` never publishes a video payload. It opens a connection,
  completes the handshake, and closes it.

## Troubleshooting

Start with:

```bash
./scripts/dry-run.sh --all
```

It names the problem rather than saying "something failed". See
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for the full catalogue.

## License

MIT. See [LICENSE](LICENSE).
