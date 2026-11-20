#!/usr/bin/env python3
"""Set stream metadata (title, game/category) across streaming platforms.

WHY A SEPARATE TOOL
-------------------
RTMP carries no metadata. The connect/publish handshake sends only the
stream key -- there is no title field, no category field, no game field.
So "updating the stream info" cannot be done through the relay. The relay
forwards video; metadata has to go through each platform's own API, as a
separate authenticated HTTP request, while the stream is live.

PLATFORM SUPPORT
----------------
    Platform    Title   Game/Category   Needs
    ---------   -----   --------------   ------------------------------------
    Twitch      yes     via category    Client-ID + OAuth user token
    Kick        yes     yes             OAuth token
    YouTube     yes     yes             OAuth2 token
    Instagram   no      no              (no public title API for RTMP)
    TikTok      no      no              (no public title API for RTMP)
    Restream    no      no              (no public API)

Twitch's "game" is the channel's category. Twitch categories are a fixed
enum, so the tool maps a free-text game name to the closest category id
via the Helix games endpoint, and reports the match so you can confirm.

CONFIG
------
Credentials live in ~/Streaming-Relay/stream-meta.env (gitignored, mode 600):

    TWITCH_CLIENT_ID=...
    TWITCH_TOKEN=...
    KICK_TOKEN=...
    TWITCH_USER_ID=...          # optional, resolved from /helix/users
    KICK_CHANNEL_SLUG=...       # optional, defaults to YOUR_HANDLE

    # defaults applied to every platform
    STREAM_TITLE=...
    STREAM_GAME=...

USAGE
-----
    ./stream-meta.sh --title "..." --game "..."              # dry run
    ./stream-meta.sh --title "..." --game "..." --apply      # actually push
    ./stream-meta.sh --check                                 # read current values
    ./stream-meta.sh --apply --only twitch,kick

The default is a DRY RUN. Metadata changes are live-visible to your
audience the instant they land, so it should be a deliberate act.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy_http import request as _request
from proxy_http import request_form as _request_form
from value_guard import explain_bad_value
from env_writer import set_values

CONFIG = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "stream-meta.env")
API_TWITCH = "https://api.twitch.tv/helix"
# Kick's API is NOT /api/v2 -- verified against api.kick.com/swagger/doc.yaml
# on 2026-11-19. The real paths are /public/v1/... and /public/v2/...
#
#   PATCH /public/v1/channels          -> update livestream metadata
#   GET   /public/v1/channels          -> read channel info
#   GET   /public/v2/categories        -> category list (v1 is deprecated)
#
# OAuth endpoint is id.kick.com, NOT api.kick.com.
API_KICK = "https://api.kick.com/public/v1"
API_KICK_CATEGORIES = "https://api.kick.com/public/v2/categories"
API_KICK_OAUTH = "https://id.kick.com"
API_YOUTUBE = "https://www.googleapis.com/youtube/v3"

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"


def load_config():
    cfg = {}
    if os.path.exists(CONFIG):
        with open(CONFIG) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                cfg[k.strip()] = v
    # env overrides the file
    for k in list(os.environ.keys()):
        if k.startswith(("TWITCH_", "KICK_", "YT_", "STREAM_")) and os.environ[k]:
            cfg[k] = os.environ[k]
    return cfg


def http(method, url, headers=None, body=None, timeout=15):
    """Returns (status, parsed_json_or_text).

    Uses the proxy-aware helper so it works both inside the OpenClaw sandbox
    (where Twitch is not on the egress allowlist) and from a normal
    terminal.
    """
    return _request(method, url, headers=headers, body=body, timeout=timeout)


# ---------------------------------------------------------------------------
# Twitch
# ---------------------------------------------------------------------------

def twitch_headers(cfg):
    cid = cfg.get("TWITCH_CLIENT_ID", "")
    tok = cfg.get("TWITCH_TOKEN", "")
    if not cid or not tok:
        return None
    return {
        "Client-Id": cid,
        "Authorization": f"Bearer {tok}",
    }


def twitch_user_id(cfg, headers):
    """Resolve the broadcaster's NUMERIC user id.

    Twitch requires broadcaster_id to be a numeric id. A login name
    like "your-handle" is rejected with:
        "The parameter 'broadcaster_id' was malformed: value must be a
         numeric"
    so a non-numeric TWITCH_USER_ID is treated as a login to resolve,
    not as an id.
    """
    configured = (cfg.get("TWITCH_USER_ID") or "").strip()
    if configured.isdigit():
        return configured

    # Ask Twitch who the token belongs to. /users honours a login.
    params = {}
    if configured:
        params["login"] = configured
    q = f"?{urllib.parse.urlencode(params)}" if params else ""
    status, data = http("GET", f"{API_TWITCH}/users{q}", headers=headers)
    if status == 200 and data.get("data"):
        uid = data["data"][0].get("id")
        if uid:
            return str(uid)
    return None


def twitch_current(cfg, headers):
    """Read current title + game name."""
    uid = twitch_user_id(cfg, headers)
    if not uid:
        return None, "could not resolve Twitch user id"
    status, data = http("GET",
                        f"{API_TWITCH}/channels?broadcaster_id={uid}",
                        headers=headers)
    if status != 200:
        return None, f"HTTP {status}: {data}"
    ch = (data.get("data") or [{}])[0]
    game = (ch.get("game_name") or "").strip()
    title = (ch.get("title") or "").strip()
    return {"title": title, "game": game}, None


def twitch_find_category(cfg, headers, game_name):
    """Map a free-text game name to a Twitch category id.

    GET /helix/search/categories?query=NAME  is the one that actually
    finds things. The older /helix/games?name= endpoint does a
    different, narrower match and MISSES real categories -- searching
    "Aniimo" returns nothing there but /search/categories returns the
    exact match with id 1267582829.

    So: try /games?name= first (exact), but always fall back to
    /search/categories?query= which is the reliable one.
    """
    name = (game_name or "").strip()
    if not name:
        return None, None

    # Exact match via /games.
    q = urllib.parse.urlencode({"name": name})
    status, data = http("GET", f"{API_TWITCH}/games?name={q}", headers=headers)
    if status == 200 and data.get("data"):
        for g in data["data"]:
            if (g.get("name") or "").lower() == name.lower():
                return g["id"], g["name"]
        g = data["data"][0]
        return g["id"], g["name"]

    # /search/categories is the reliable lookup.
    q = urllib.parse.urlencode({"query": name})
    status, data = http("GET", f"{API_TWITCH}/search/categories?{q}",
                        headers=headers)
    if status == 200 and data.get("data"):
        cats = data["data"]
        low = name.lower()
        for c in cats:
            if (c.get("name") or "").lower() == low:
                return c["id"], c["name"]
        for c in cats:
            if (c.get("name") or "").lower().startswith(low):
                return c["id"], c["name"]
        c = cats[0]
        return c["id"], c["name"]

    # Last resort: /games on the first word.
    word = name.split()[0]
    q = urllib.parse.urlencode({"name": word})
    status, data = http("GET", f"{API_TWITCH}/games?name={q}", headers=headers)
    if status == 200 and data.get("data"):
        games = data["data"]
        low = name.lower()
        for g in games:
            if (g.get("name") or "").lower() == low:
                return g["id"], g["name"]
        for g in games:
            if (g.get("name") or "").lower().startswith(low):
                return g["id"], g["name"]
        return games[0]["id"], games[0]["name"]
    return None, None


def twitch_set_title(cfg, headers, title):
    uid = twitch_user_id(cfg, headers)
    if not uid:
        return False, "could not resolve Twitch user id"
    status, data = http(
        "PATCH",
        f"{API_TWITCH}/channels?broadcaster_id={uid}",
        headers=headers,
        body={"title": title},
    )
    if status in (200, 204):
        return True, "title updated"
    return False, f"HTTP {status}: {data}"


def twitch_set_game(cfg, headers, game_name):
    cat_id, matched = twitch_find_category(cfg, headers, game_name)
    if not cat_id:
        return False, f"no Twitch category found for {game_name!r}"
    uid = twitch_user_id(cfg, headers)
    if not uid:
        return False, "could not resolve Twitch user id"
    status, data = http(
        "PATCH",
        f"{API_TWITCH}/channels?broadcaster_id={uid}",
        headers=headers,
        body={"game_id": cat_id},
    )
    if status in (200, 204):
        return True, f"category set to {matched!r} (id {cat_id})"
    return False, f"HTTP {status}: {data}"


# ---------------------------------------------------------------------------
# Kick
# ---------------------------------------------------------------------------

def kick_headers(cfg):
    tok = cfg.get("KICK_TOKEN", "")
    if not tok:
        return None
    return {"Authorization": f"Bearer {tok}"}


def kick_slug(cfg):
    return cfg.get("KICK_CHANNEL_SLUG", "YOUR_HANDLE")


def kick_current(cfg, headers):
    """Read current title + category.

    GET /public/v1/channels?slug=SLUG
    With NO parameters it returns the channel of the authenticated user,
    which is usually simpler than passing a slug.
    """
    slug = kick_slug(cfg)
    status, data = http("GET", f"{API_KICK}/channels?slug={urllib.parse.quote(slug)}",
                        headers=headers)
    if status != 200:
        # Fall back to "the authenticated user" form.
        status, data = http("GET", f"{API_KICK}/channels", headers=headers)
    if status != 200:
        return None, f"HTTP {status}: {data}"
    items = data.get("data") or []
    if not items:
        return None, "no channel returned"
    ch = items[0]
    livestream = ch.get("livestream") or {}
    categories = ch.get("categories") or []
    return {
        "title": ch.get("stream_title") or livestream.get("session_title", "")
                  or livestream.get("title", ""),
        "game": categories[0].get("name", "") if categories else "",
        "live": bool(livestream),
        "id": ch.get("user_id") or ch.get("id"),
    }, None


def kick_set_title(cfg, headers, title):
    """PATCH /public/v1/channels with stream_title.

    Kick requires the channel to be identified. channel_slug works and
    is what the token is already scoped to; without it the API answers
    400 "Invalid request".
    """
    slug = kick_slug(cfg)
    body = {"channel_slug": slug, "stream_title": title}
    status, data = http("PATCH", f"{API_KICK}/channels",
                        headers=headers, body=body)
    if status in (200, 204):
        return True, "title updated"
    return False, f"HTTP {status}: {data}"


def kick_set_game(cfg, headers, game_name):
    """PATCH /public/v1/channels with category_id.

    Kick categories are a fixed enum, so we look the name up first.
    GET /public/v2/categories?name=NAME
    """
    name = (game_name or "").strip()
    status, data = http("GET", f"{API_KICK_CATEGORIES}?name={urllib.parse.quote(name)}",
                        headers=headers)
    cats = (data.get("data") or []) if isinstance(data, dict) else []
    if not cats:
        # Try a looser search on the first word.
        word = name.split()[0]
        status, data = http(
            "GET",
            f"{API_KICK_CATEGORIES}?name={urllib.parse.quote(word)}",
            headers=headers)
        cats = (data.get("data") or []) if isinstance(data, dict) else []
        if cats:
            low = name.lower()
            for c in cats:
                if (c.get("name") or "").lower() == low:
                    cats = [c]
                    break
            else:
                cats = [cats[0]]

    if not cats:
        return False, f"no Kick category found for {game_name!r}"

    cat = cats[0]
    cid = cat.get("id")
    slug = kick_slug(cfg)
    body = {"channel_slug": slug, "category_id": cid}
    status, data = http("PATCH", f"{API_KICK}/channels",
                        headers=headers, body=body)
    if status in (200, 204):
        return True, f"category set to {cat.get('name')!r} (id {cid})"
    return False, f"HTTP {status}: {data}"


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------

def youtube_refresh(cfg):
    """Refresh an expired YouTube access token using the refresh token.

    YouTube access tokens last 1 hour. The refresh token does not
    expire, so this makes the setup a one-time browser flow rather than
    an hourly one. Returns (ok, message).
    """
    rt = cfg.get("YT_REFRESH_TOKEN", "")
    cid = cfg.get("YT_CLIENT_ID", "")
    secret = cfg.get("YT_CLIENT_SECRET", "")
    if not rt or not cid or not secret:
        return False, ("need YT_REFRESH_TOKEN, YT_CLIENT_ID and "
                       "YT_CLIENT_SECRET to refresh")

    body = {
        "grant_type": "refresh_token",
        "client_id": cid,
        "client_secret": secret,
        "refresh_token": rt,
    }
    status, data = _request_form("POST", "https://oauth2.googleapis.com/token",
                                  body, timeout=20)
    if status == 200 and isinstance(data, dict) and data.get("access_token"):
        new_tok = data["access_token"]
        _save_config_value("YT_TOKEN", new_tok)
        if data.get("refresh_token"):
            _save_config_value("YT_REFRESH_TOKEN", data["refresh_token"])
        return True, (f"token refreshed (valid {data.get('expires_in')}s), "
                      f"saved to {CONFIG}")
    return False, f"HTTP {status}: {data}"


def kick_refresh(cfg, headers):
    """Refresh an expired Kick access token using the refresh token.

    Kick access tokens last 2 hours. The refresh token lasts 30 days on a
    sliding window. Returns (ok, message).
    """
    rt = cfg.get("KICK_REFRESH_TOKEN", "")
    cid = cfg.get("KICK_CLIENT_ID", "")
    secret = cfg.get("KICK_CLIENT_SECRET", "")
    if not rt or not cid or not secret:
        return False, ("need KICK_REFRESH_TOKEN, KICK_CLIENT_ID and "
                       "KICK_CLIENT_SECRET to refresh")

    body = {
        "grant_type": "refresh_token",
        "client_id": cid,
        "client_secret": secret,
        "refresh_token": rt,
        "redirect_uri": "https://localhost",
    }
    status, data = _request_form("POST", f"{API_KICK_OAUTH}/oauth/token", body,
                                  timeout=20)
    if status == 200 and isinstance(data, dict) and data.get("access_token"):
        new_tok = data["access_token"]
        new_rt = data.get("refresh_token") or rt
        _save_config_value("KICK_TOKEN", new_tok)
        if data.get("refresh_token"):
            _save_config_value("KICK_REFRESH_TOKEN", new_rt)
        return True, (f"token refreshed (valid {data.get('expires_in')}s), "
                      f"saved to {CONFIG}")
    return False, f"HTTP {status}: {data}"


def _save_config_value(key, value):
    """Update a single key in the config file, preserving everything else.

    Delegates to env_writer.set_values so there is ONE implementation of
    the credential-file write. The earlier local copy of this logic did
    not create the temp file with mode 600, so the credentials were
    briefly world-readable between the write and the replace.
    """
    if not os.path.exists(CONFIG):
        return False
    ok, _msg = set_values(CONFIG, {key: value})
    return ok


def youtube_headers(cfg):
    tok = cfg.get("YT_TOKEN", "")
    if not tok:
        return None
    headers = {"Authorization": f"Bearer {tok}"}
    # The API key is optional but helps on read calls.
    key = cfg.get("YT_API_KEY", "")
    if key:
        headers["X-Goog-Api-Key"] = key
    return headers


def youtube_resolve_channel(cfg):
    """Resolve YT_CHANNEL_ID from the handle if only the handle is set.

    Uses the API key against channels/forHandle. Returns the UC... id
    or None.
    """
    channel = cfg.get("YT_CHANNEL_ID", "")
    handle = cfg.get("YT_CHANNEL_HANDLE", "")
    if channel.startswith("UC"):
        return channel
    if not handle:
        return None
    key = cfg.get("YT_API_KEY", "")
    if not key:
        return None
    q = urllib.parse.urlencode({"forHandle": handle.lstrip("@"), "key": key})
    status, data = http("GET", f"{API_YOUTUBE}/channels?{q}")
    if status != 200:
        return None
    items = data.get("items") or []
    if not items:
        return None
    return items[0].get("id")


def youtube_current(cfg, headers):
    # Find the active broadcast for this channel.
    channel = cfg.get("YT_CHANNEL_ID", "")
    if not channel.startswith("UC"):
        channel = youtube_resolve_channel(cfg) or ""
    if not channel:
        return None, "YT_CHANNEL_ID not set (and handle lookup needs YT_API_KEY)"

    # `broadcastStatus` and `mine` are MUTUALLY EXCLUSIVE. Passing both
    # gives:
    #   400 "Incompatible parameters specified in the request:
    #        broadcastStatus, mine"
    # Use mine=true alone -- it means "my broadcasts", and we filter
    # for the live one ourselves.
    q = urllib.parse.urlencode({
        "part": "snippet,contentDetails",
        "mine": "true",
    })
    status, data = http("GET", f"{API_YOUTUBE}/liveBroadcasts?{q}", headers=headers)
    if status != 200:
        return None, f"HTTP {status}: {data}"
    items = data.get("items") or []
    if not items:
        return None, "no active broadcast"
    b = items[0]
    # `items` from mine=true includes recent non-live broadcasts.
    # Prefer the one whose snippet says it is live.
    live = None
    for it in items:
        snip = it.get("snippet", {})
        if snip.get("actualEndTime") in (None, "") and \
                snip.get("actualStartTime") not in (None, ""):
            live = it
            break
    if live is None:
        live = b
    b = live
    return {
        "title": b.get("snippet", {}).get("title", ""),
        "game": b.get("snippet", {}).get("categoryId", ""),
        "id": b.get("id"),
    }, None


def youtube_set(cfg, headers, title, category_id):
    # Find the broadcast to update. An explicit YT_BROADCAST_ID wins;
    # otherwise discover the live one.
    broadcast_id = (cfg.get("YT_BROADCAST_ID") or "").strip()
    snippet = None
    if not broadcast_id:
        current, err = youtube_current(cfg, headers)
        if not current:
            return False, f"could not find a broadcast to update: {err}"
        broadcast_id = current.get("id", "")
        if not broadcast_id:
            return False, "could not find a broadcast to update"

    # A PUT REPLACES the resource. Sending only {title} gets rejected:
    #   "Id is required"
    #   "Scheduled start time is required"
    # So fetch the existing snippet and send it back with the title
    # (and category) changed.
    q_read = urllib.parse.urlencode({"part": "snippet", "id": broadcast_id})
    st_read, data_read = http("GET", f"{API_YOUTUBE}/liveBroadcasts?{q_read}",
                              headers=headers)
    if st_read == 200 and data_read.get("items"):
        snippet = dict(data_read["items"][0].get("snippet", {}))
    if snippet is None:
        snippet = {}

    snippet["title"] = title
    if category_id:
        snippet["categoryId"] = category_id

    body = {"id": broadcast_id, "snippet": snippet}

    q = urllib.parse.urlencode({
        "part": "snippet",
        "id": broadcast_id,
    })
    status, data = http("PUT", f"{API_YOUTUBE}/liveBroadcasts?{q}",
                        headers=headers, body=body)
    if status == 200:
        return True, "updated"
    return False, f"HTTP {status}: {data}"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

PLATFORMS = ("twitch", "kick", "youtube")
NO_TITLE_API = {
    "instagram": "no public title API for RTMP ingest",
    "tiktok": "no public title API for RTMP ingest",
    "restream": "no public API",
}


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--title", help="stream title")
    ap.add_argument("--game", help="game name / category")
    ap.add_argument("--apply", action="store_true",
                    help="actually push the changes (default is a dry run)")
    ap.add_argument("--check", action="store_true",
                    help="show current title/game per platform")
    ap.add_argument("--only", help="comma-separated platform list")
    ap.add_argument("--config", default=CONFIG)
    args = ap.parse_args()

    cfg = load_config()
    if args.config != CONFIG:
        if os.path.exists(args.config):
            with open(args.config) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        cfg[k.strip()] = v.strip().strip('"').strip("'")

    title = args.title or cfg.get("STREAM_TITLE", "")
    game = args.game or cfg.get("STREAM_GAME", "")

    only = None
    if args.only:
        only = [p.strip().lower() for p in args.only.split(",") if p.strip()]

    def wanted(p):
        return only is None or p in only

    print(f"{BOLD}=== Stream metadata ==={NC}\n")

    if args.check:
        print(f"{BOLD}Current values{NC}")
        for p in PLATFORMS:
            if not wanted(p):
                continue
            if p == "twitch":
                h = twitch_headers(cfg)
                if not h:
                    print(f"  {YELLOW}twatch{NC}: no credentials in {CONFIG}")
                    continue
                cur, err = twitch_current(cfg, h)
                if err:
                    print(f"  {RED}twitch{NC}: {err}")
                    continue
                print(f"  twitch : title={cur['title']!r}  game={cur['game']!r}")
            elif p == "kick":
                h = kick_headers(cfg)
                if not h:
                    print(f"  {YELLOW}kick{NC}: no credentials in {CONFIG}")
                    continue
                cur, err = kick_current(cfg, h)
                # Kick access tokens live 2 hours. The refresh token
                # lives 30 days on a sliding window, so refresh once and
                # retry before reporting a failure.
                if err and "401" in err:
                    good2, r2 = kick_refresh(cfg, h)
                    if good2:
                        h = kick_headers(cfg)
                        cur, err = kick_current(cfg, h)
                        err = f"{r2}" if err is None else err
                if err:
                    print(f"  {RED}kick{NC}: {err}")
                    continue
                print(f"  kick   : title={cur['title']!r}  game={cur['game']!r}  live={cur['live']}")
            elif p == "youtube":
                h = youtube_headers(cfg)
                if not h:
                    print(f"  {YELLOW}youtube{NC}: no credentials in {CONFIG}")
                    continue
                cur, err = youtube_current(cfg, h)
                # An expired token reads as "no broadcast" or a 401.
                # The refresh token does not expire, so refresh once and
                # retry before reporting a failure.
                if err and ("401" in err or "Invalid" in err or
                            "UNAUTHENTICATED" in err):
                    good2, r2 = youtube_refresh(cfg)
                    if good2:
                        h = youtube_headers(cfg)
                        cur, err = youtube_current(cfg, h)
                        err = f"{r2}" if err is None else err
                if err:
                    print(f"  {RED}youtube{NC}: {err}")
                    continue
                print(f"  youtube: title={cur['title']!r}  category={cur['game']!r}")
        print()
        print(f"{DIM}No title API: " + ", ".join(
            f"{k} ({v})" for k, v in NO_TITLE_API.items()) + f"{NC}")
        return 0

    if not title and not game:
        print(f"{RED}error{NC}: give --title and/or --game (or set STREAM_TITLE/STREAM_GAME)")
        return 1

    mode = f"{RED}APPLY{NC}" if args.apply else f"{YELLOW}DRY RUN{NC}"
    print(f"{BOLD}Mode:{NC} {mode}")
    print(f"{BOLD}Title:{NC} {title!r}")
    print(f"{BOLD}Game:{NC}  {game!r}")
    print()

    results = []

    # -- Twitch ------------------------------------------------------------
    if wanted("twitch"):
        h = twitch_headers(cfg)
        if not h:
            results.append(("twitch", False,
                            f"no TWITCH_CLIENT_ID / TWITCH_TOKEN in {CONFIG}"))
        else:
            bad = explain_bad_value(cfg.get("TWITCH_TOKEN", ""), "Twitch")
            if bad:
                results.append(("twitch", False, bad))
            else:
                # Resolve the category first so the dry run shows the real target.
                if game:
                    cat_id, matched = twitch_find_category(cfg, h, game)
                    if not cat_id:
                        results.append(("twitch", False,
                                        f"no category match for {game!r}"))
                    elif matched and matched.lower() != game.lower():
                        results.append(("twitch", None,
                                        f"category {game!r} -> {matched!r} (id {cat_id})"))
                if title:
                    results.append(("twitch", None, f"title -> {title!r}"))

    # -- Kick --------------------------------------------------------------
    if wanted("kick"):
        h = kick_headers(cfg)
        if not h:
            results.append(("kick", False,
                            f"no KICK_TOKEN in {CONFIG}"))
        else:
            bad = explain_bad_value(cfg.get("KICK_TOKEN", ""), "Kick")
            if bad:
                results.append(("kick", False, bad))
            else:
                if title:
                    results.append(("kick", None, f"title -> {title!r}"))
                if game:
                    results.append(("kick", None, f"category -> {game!r}"))

    # -- YouTube -----------------------------------------------------------
    if wanted("youtube"):
        h = youtube_headers(cfg)
        if not h:
            results.append(("youtube", False,
                            f"no YT_TOKEN in {CONFIG}"))
        else:
            if title:
                results.append(("youtube", None, f"title -> {title!r}"))

    if not results:
        print(f"{DIM}No supported platform selected.{NC}")
        return 1

    print(f"{BOLD}Plan{NC}")
    for p, ok, msg in results:
        mark = f"{GREEN}✓{NC}" if ok is True else (f"{YELLOW}~{NC}" if ok is None else f"{RED}✗{NC}")
        print(f"  {mark} {p:8} {msg}")
    print()

    if not args.apply:
        print(f"{YELLOW}dry run — nothing was changed.{NC}")
        print(f"  re-run with {BOLD}--apply{NC} to push these updates live.")
        print(f"  {DIM}metadata changes are visible to your audience immediately.{NC}")
        return 0

    print(f"{BOLD}Applying{NC}")
    failed = 0
    for p, ok, msg in results:
        if ok is False:
            print(f"  {RED}✗{NC} {p:8} {msg}")
            failed += 1
            continue

        h = twitch_headers(cfg) if p == "twitch" else (
            kick_headers(cfg) if p == "kick" else youtube_headers(cfg))
        try:
            if p == "twitch":
                if title:
                    good, r = twitch_set_title(cfg, h, title)
                    if not good:
                        raise RuntimeError(r)
                    print(f"  {GREEN}✓{NC} {p:8} {r}")
                if game:
                    cat_id, matched = twitch_find_category(cfg, h, game)
                    if cat_id:
                        good, r = twitch_set_game(cfg, h, game)
                        if not good:
                            raise RuntimeError(r)
                        print(f"  {GREEN}✓{NC} {p:8} {r}")
            elif p == "kick":
                # Kick access tokens live 2 hours. If the first call comes
                # back 401, try the refresh token once before giving up.
                if title:
                    good, r = kick_set_title(cfg, h, title)
                    if not good and "401" in r:
                        good2, r2 = kick_refresh(cfg, h)
                        if good2:
                            h = kick_headers(cfg)
                            good, r = kick_set_title(cfg, h, title)
                            r = f"{r2}; {r}"
                    if not good:
                        raise RuntimeError(r)
                    print(f"  {GREEN}✓{NC} {p:8} {r}")
                if game:
                    good, r = kick_set_game(cfg, h, game)
                    if not good and "401" in r:
                        good2, r2 = kick_refresh(cfg, h)
                        if good2:
                            h = kick_headers(cfg)
                            good, r = kick_set_game(cfg, h, game)
                            r = f"{r2}; {r}"
                    if not good:
                        raise RuntimeError(r)
                    print(f"  {GREEN}✓{NC} {p:8} {r}")
            elif p == "youtube":
                # YouTube access tokens live 1 hour. If the first call
                # comes back 401, refresh once using the refresh token
                # (which does not expire) before giving up.
                if title:
                    good, r = youtube_set(cfg, h, title, cfg.get("YT_CATEGORY_ID"))
                    if not good and "401" in r:
                        good2, r2 = youtube_refresh(cfg)
                        if good2:
                            h = youtube_headers(cfg)
                            good, r = youtube_set(cfg, h, title,
                                                 cfg.get("YT_CATEGORY_ID"))
                            r = f"{r2}; {r}"
                    if not good:
                        raise RuntimeError(r)
                    print(f"  {GREEN}✓{NC} {p:8} {r}")
        except Exception as e:
            print(f"  {RED}✗{NC} {p:8} {e}")
            failed += 1

    print()
    print(f"{DIM}No title API: " + ", ".join(
        f"{k} ({v})" for k, v in NO_TITLE_API.items()) + f"{NC}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
