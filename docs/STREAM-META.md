# Stream Metadata

Setting the stream title and category across YouTube, Twitch, and Kick from
one command.

**RTMP carries no metadata.** The title and category travel over the
platform's own API, not through the stream. That is why this is a separate
layer from the relay itself.

---

## Quick start

```bash
cd tools

./kick-token.sh       # opens a browser, saves the token for you
./twitch-token.sh
./youtube-token.sh

cd ..
./tools/stream-meta.sh --title "My stream title" --game "Just Chatting"
```

The token helpers **write the config file themselves**. Do not copy and
paste credential values by hand — an OAuth authorization code and an access
token look nearly identical, and pasting the wrong one gives a confusing
401 with no useful message.

---

## Commands

```bash
# Show the current title and category everywhere
./tools/stream-meta.sh --check

# Preview a change without applying it (this is the default)
./tools/stream-meta.sh --title "New title" --game "Gaming"

# Apply it
./tools/stream-meta.sh --apply --title "New title" --game "Gaming"

# Only some platforms
./tools/stream-meta.sh --apply --only twitch,kick --title "New title"
```

`--check` is safe to run any time.

Without `--apply`, the tool only prints what it *would* change.

---

## Which platforms work

| Platform | Title | Category | Notes |
|---|---|---|---|
| YouTube | ✅ | ✅ | Category is a numeric id |
| Twitch | ✅ | ✅ | Twitch's "game" **is** its category |
| Kick | ✅ | ✅ | Categories are a fixed enum |
| Instagram | ❌ | ❌ | No public metadata API for RTMP ingest |
| TikTok | ❌ | ❌ | No public metadata API for RTMP ingest |
| Restream | ❌ | ❌ | No public metadata API |

---

## Credential setup

### Twitch

1. Create an app at <https://dev.twitch.tv/console/apps>
2. Copy the **Client ID**
3. The helper opens an authorization URL with the
   `channel:manage:broadcast` scope
4. Approve it, paste the redirect URL back
5. The token is written to `stream-meta.env` as `TWITCH_TOKEN`

```bash
./tools/twitch-token.sh --client-id YOUR_CLIENT_ID
```

The helper reads `TWITCH_CLIENT_ID` from the config if you leave the flag
off.

### Kick

1. Create an app at <https://dev.kick.com/applications>
2. Copy the **Client ID** and **Client Secret**
3. Set the redirect URL to `https://localhost`
4. The helper opens an authorization URL
5. Approve it, paste the redirect URL back
6. The tokens are written as `KICK_TOKEN` and `KICK_REFRESH_TOKEN`

```bash
./tools/kick-token.sh
```

The helper reads `KICK_CLIENT_ID` and `KICK_CLIENT_SECRET` from the config
if you leave the flags off.

Kick access tokens last 2 hours. The refresh token lasts 30 days on a
sliding window.

### YouTube

YouTube needs **two** credentials, and they do different jobs:

| Credential | Grants | Needed for |
|---|---|---|
| API key | Public reads | Channel lookup, category list |
| OAuth token | Act as the channel | **Changing** a title or category |

The API key alone can never change your stream title.

1. **Enable the API.** Google Cloud Console → your project → **APIs &
   Services** → **Library** → **YouTube Data API v3** → **Enable**.
   Creating a key does not enable the API. These are separate actions.
2. **Create an API key.** Credentials → Create Credentials → API key →
   **Public data** → name it → create. Copy the key.
3. **Create an OAuth client.** Credentials → Create Credentials → OAuth
   client ID → **Web application** → redirect URI `https://localhost`.
4. Put both in `stream-meta.env`:

```
YT_API_KEY=AIzaSy...
YT_CLIENT_ID=xxxxx.apps.googleusercontent.com
YT_CLIENT_SECRET=GOCSPX-...
```

5. Run the helper:

```bash
./tools/youtube-token.sh
```

It opens a browser, you approve, and it writes `YT_TOKEN` and
`YT_REFRESH_TOKEN`.

**The redirect lands on `https://localhost`, which will not load.** That is
expected — the URL bar still contains `?code=...`. Copy the whole address
and paste it back.

#### The OAuth consent screen

A new OAuth client defaults to **publishing status = Testing**. Only
accounts on the test-user list can use it, and Google shows a large "Access
blocked" banner even to the developer.

**Fix (2 minutes):** Google Cloud Console → project → **APIs & Services** →
**OAuth consent screen** → **Test users** → **Add users** → your Google
account.

Do not chase production publishing for a personal tool. It requires a
verified domain, a public privacy policy, an app homepage, and a demo
video.

---

## The config file

`stream-meta.env`, mode `600`:

```
# --- Twitch ---
TWITCH_CLIENT_ID=
TWITCH_TOKEN=
TWITCH_USER_ID=
TWITCH_CHANNEL_LOGIN=

# --- Kick ---
KICK_CLIENT_ID=
KICK_CLIENT_SECRET=
KICK_TOKEN=
KICK_REFRESH_TOKEN=
KICK_CHANNEL_SLUG=

# --- YouTube ---
YT_CLIENT_ID=
YT_CLIENT_SECRET=
YT_TOKEN=
YT_REFRESH_TOKEN=
YT_API_KEY=
YT_CHANNEL_ID=
YT_CHANNEL_HANDLE=
YT_BROADCAST_ID=
YT_CATEGORY_ID=
```

---

## API quirks worth knowing

These are the things that cost real time to figure out. Each one produced a
specific error message.

### Twitch needs a numeric broadcaster_id

```
The parameter "broadcaster_id" was malformed: value must be a numeric
```

`TWITCH_USER_ID` must be the numeric id, not the login name. The tool
resolves a non-numeric value through `GET /helix/users?login=...`:

```bash
./tools/resolve-twitch-uid.sh
```

### Twitch category lookup needs the search endpoint

`GET /helix/games?name=X` does a narrower match than
`GET /helix/search/categories?query=X`. A category that definitely exists
can be invisible to the first endpoint. The tools use the search endpoint.

### YouTube: `broadcastStatus` and `mine` are mutually exclusive

```
Incompatible parameters specified in the request: broadcastStatus, mine
```

Use `mine=true` alone.

### YouTube: a PUT replaces the whole resource

Sending only the changed field gives:

```
Id is required
Scheduled start time is required
```

Read the existing snippet, change one field, send it all back.

### Kick PATCH needs `channel_slug`

```
{"stream_title": "..."}       -> 400 Invalid request
{"channel_slug": "...", ...}  -> 204
```

### Kick applies channel writes only while live

A `PATCH` to an offline channel returns `204` and changes nothing —
including plain channel fields like the description. This is not a scope
problem; a missing scope gives `401` or `403`.

### YouTube broadcasts only exist while streaming

`mine=true` returns your recent broadcasts, but a live broadcast is only
created when a stream key is used. With no stream running, there is nothing
live to update.

---

## Verifying it works

```bash
cd tools
./test-write-all.sh
```

This exercises the real setter functions against the live APIs and writes
the current values back, so nothing visibly changes.

```
  twitch :
  PASS  read current title
  PASS  write title (no-op)
  PASS  write category (no-op)

  kick   :
  PASS  read current title
  PASS  write accepted (channel offline -- 204 = accepted)

  youtube:
  PASS  read current broadcast
  PASS  write title (no-op)
```

For Kick, run it while the channel is live to get the full write/read-back
check.

Other diagnostics:

```bash
./tools/check-twitch-state.sh     # token scopes + live state
./tools/check-kick-state.sh        # live state
./tools/check-youtube-client.sh    # are the OAuth credentials valid
./tools/check-youtube-redirect.sh  # which redirect URI is registered
./tools/check-youtube-api-key.sh   # does the API key work
```

---

## Refreshing an expired token

```bash
./tools/kick-token.sh
```

Re-running the helper replaces the token in place and backs up the config
first. The writer preserves comments, key order, and file mode.

---

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for the full catalogue. The
most common:

| Symptom | Cause |
|---|---|
| `401 Invalid OAuth token` | Expired token, or an authorization code pasted where a token belongs |
| `403 Permission denied on the service` | YouTube API key, and the Data API v3 is not enabled on the project |
| `redirect_uri_mismatch` | The redirect URI does not match the registered one exactly |
| `Access blocked ... verification process` | The OAuth app is in Testing mode and your account is not a test user |
| `400 Invalid request` (Kick) | `channel_slug` missing from the PATCH body |
| `204` but nothing changed (Kick) | The channel is not live |
