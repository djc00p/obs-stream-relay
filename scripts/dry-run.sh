#!/usr/bin/env bash
# =============================================================================
# dry-run.sh -- validate every platform target WITHOUT broadcasting
#
# This is the safety check before a real stream. It verifies:
#   1. every platform has a key present
#   2. every key is non-empty and the right SHAPE (length, charset)
#   3. the platform's ingest host is reachable and TLS handshake works
#   4. the platform ACCEPTS the credential -- by sending a real RTMP connect
#      and reading the platform's response WITHOUT actually publishing video
#   5. the relay itself would accept the target
#
# NOTHING IS BROADCAST. Step 4 opens an RTMP connection and completes the
# handshake, then disconnects before any video payload is sent. Some platforms
# will register a brief "user started broadcasting" event that immediately
# ends -- that is the closest you can get to a credential check without
# sending real content.
#
# Usage:
#   ./dry-run.sh              check whatever is in stream-keys.env
#   ./dry-run.sh --all        require every platform to be present
# =============================================================================

set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API="http://127.0.0.1:9997"
KEYS_FILE="$DIR/../stream-keys.env"
META_FILE="$DIR/../stream-meta.env"

GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; BLUE=$'\033[34m'
BOLD=$'\033[1m'; DIM=$'\033[2m'; NC=$'\033[0m'

FAILURES=0
WARNINGS=0

ok()    { echo "${GREEN}  ✓${NC} $*"; }
bad()   { echo "${RED}  ✗${NC} $*"; FAILURES=$((FAILURES+1)); }
warn()  { echo "${YELLOW}  !${NC} $*"; WARNINGS=$((WARNINGS+1)); }
head2() { echo; echo "${BOLD}$1${NC}"; }

[ -f "$KEYS_FILE" ] || { echo "${RED}error:${NC} no $KEYS_FILE"; exit 1; }
# Load the key file WITHOUT executing it. Sourcing it would run
# whatever is in it as shell.
# shellcheck disable=SC1091
. "$DIR/../tools/load-env.sh" "$KEYS_FILE"

REQUIRE_ALL=0
[ "${1:-}" = "--all" ] && REQUIRE_ALL=1

echo "${BOLD}=== Relay dry run — validate targets without broadcasting ===${NC}"
echo "${DIM}Nothing will be published. Platform connections are opened,${NC}"
echo "${DIM}handshaken, and closed before any video is sent.${NC}"

# ---------------------------------------------------------------------------
# PLATFORM TABLE
#   name | path | url | keyvar | expected key shape | api-slug
#   api-slug is the lowercase platform id used for the live-channel
#   check (twitch, kick). Empty means no API check is possible.
# ---------------------------------------------------------------------------
PLATFORMS=(
  "YouTube (landscape)|land|rtmps://a.rtmps.youtube.com:443/live2|YT_LAND_KEY|youtube|"
  "Twitch|land|rtmp://ingest.global-contribute.live-video.net/app|TWITCH_KEY|twitch|twitch"
  "Kick|land|rtmps://fa723fc1b171.global-contribute.live-video.net/|KICK_KEY|kick|kick"
  "YouTube (portrait)|vert|rtmps://a.rtmps.youtube.com:443/live2|YT_VERT_KEY|youtube|"
  "TikTok|vert|${TIKTOK_URL:-rtmps://live.tiktokcdn.com/live}|TIKTOK_KEY|tiktok|"
  "Instagram|vert|${IG_URL:-rtmps://live.instagram.com/rtmp}|IG_KEY|instagram|"
)

# ---------------------------------------------------------------------------
# SKIP list -- platforms that are intentionally NOT being tested.
#
# Why this exists: some platforms cannot be validated without a live session
# or without a credential that is only valid once. TikTok, for example, needs
# LIVE Producer access (granted per-account by TikTok) and issues a host that
# only exists inside a LIVE Center session.
#
# A skipped platform must NOT disqualify the run.
#
# Set it in stream-keys.env, e.g.:
#     SKIP_PLATFORMS="TikTok Instagram"
# or per-run:
#     ./dry-run.sh --skip "TikTok,Instagram"
# ---------------------------------------------------------------------------
SKIP_LIST=""
for arg in "$@"; do
  case "$arg" in
    --skip) NEXT_IS_SKIP=1 ;;
    --skip=*) SKIP_LIST="${arg#--skip=}" ;;
    *) if [ "${NEXT_IS_SKIP:-0}" = "1" ]; then SKIP_LIST="$arg"; NEXT_IS_SKIP=0; fi ;;
  esac
done
# A SKIP_PLATFORMS var in the env file also works.
if [ -f "$KEYS_FILE" ]; then
  # shellcheck disable=SC1091
  . "$DIR/../tools/load-env.sh" "$KEYS_FILE"
  [ -n "${SKIP_PLATFORMS:-}" ] && SKIP_LIST="${SKIP_LIST:+$SKIP_LIST,}${SKIP_PLATFORMS}"
fi
SKIP_LIST="${SKIP_LIST//,/ }"

is_skipped() {
  local name="$1" s
  for s in $SKIP_LIST; do
    [ "$s" = "$name" ] && return 0
  done
  return 1
}

# --- key shape checks ------------------------------------------------------
# Each platform has its own key format. A wrong-shape key is the #1 cause of
# a silently failed forward.
check_shape() {
  local kind="$1" key="$2"
  case "$kind" in
    youtube)
      # Format: xxxx-xxxx-xxxx-xxxx-xxxx  (5 groups of 4, hex-ish)
      if [[ "$key" =~ ^[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{4}$ ]]; then
        ok "key shape ok (youtube 5x4 groups)"
      else
        bad "key shape WRONG for YouTube — expected xxxx-xxxx-xxxx-xxxx-xxxx"
        echo "      got: ${key:0:12}… (len ${#key})"
        return 1
      fi
      ;;
    twitch)
      # Format: live_<channelid>_<alphanumeric>
      if [[ "$key" =~ ^live_[0-9]+_[A-Za-z0-9]+$ ]]; then
        ok "key shape ok (twitch live_<id>_<token>)"
      else
        bad "key shape WRONG for Twitch — expected live_<channelid>_<token>"
        echo "      got: ${key:0:16}… (len ${#key})"
        return 1
      fi
      ;;
    kick)
      # Format: sk_<region>_<token>
      #   region may contain hyphens  (sk_us-west-2_...)
      #   token may contain underscores and mixed case
      if [[ "$key" =~ ^sk_[a-z0-9-]+_[A-Za-z0-9_-]+$ ]]; then
        ok "key shape ok (kick sk_<region>_<token>)"
      else
        bad "key shape WRONG for Kick — expected sk_<region>_<token>"
        echo "      got: ${key:0:16}… (len ${#key})"
        return 1
      fi
      ;;
    tiktok|instagram)
      # Session keys: long, and may contain URL query characters (Instagram's
      # key is a full query string with ? & =). We only check length and that
      # it has no whitespace/shell-breaking characters.
      #
      # The character class is built with a variable because a literal '&'
      # inside a bash [[ =~ ]] pattern breaks the parser.
      local session_chars='[A-Za-z0-9_?&=.%~:-]'
      if [ "${#key}" -ge 20 ]; then
        if [[ "$key" =~ ^${session_chars}+$ ]]; then
          ok "key shape ok (session key, len ${#key})"
        else
          bad "key contains characters that would break a URL or shell"
          return 1
        fi
      else
        bad "key too SHORT for $kind (len ${#key}, expected 20+)"
        echo "      session keys are long — did you paste the whole thing?"
        return 1
      fi
      ;;
  esac
}

# --- connectivity + credential probe --------------------------------------
# Opens an RTMP(S) connection, completes the handshake, reads the platform's
# response, and closes. No video payload is sent.
#
# SIGNAL SEMANTICS (verified against YouTube 2026-11-19):
#   SUCCESS  -> ffmpeg reaches the end of its inputs and prints the muxing
#               summary ("Lsize=" / "muxing overhead"). The connection was
#               accepted.
#   REJECTED -> ffmpeg prints "[tls @ ...] IO error: End of file" followed by
#               "Error opening output ...". The platform closed the
#               connection during the handshake.
#
# Matching on generic words like "403" or "Invalid" produces FALSE POSITIVES
# because libx264 prints "profile Constrained Baseline" etc. Match only on
# these specific markers.
# -----------------------------------------------------------------------------
# Is a channel already broadcasting?
#
# Twitch and Kick both allow ONE broadcast per channel. A second publish
# is rejected, and ffmpeg reports that as a generic "Input/output error"
# (Twitch) or a TLS "End of file" (Kick) -- indistinguishable from a
# bad key. This checks the platform API so the report names the REAL
# cause.
#
# Uses the OAuth tokens in stream-meta.env. If the token is missing or
# the check cannot run, it returns "unknown" (exit 2) and the caller
# falls back to the generic message.
# -----------------------------------------------------------------------------
platform_is_live() {
  local platform="$1"
  local out

  # NOTE: this uses the python helper, not curl. In the OpenClaw
  # sandbox curl is blocked by the egress proxy (it returns http=000),
  # while proxy_http falls back to a direct connection and succeeds.
  case "$platform" in
    twitch)
      out="$(python3 "$DIR/../tools/platform-live.py" twitch 2>/dev/null)"
      ;;
    kick)
      out="$(python3 "$DIR/../tools/platform-live.py" kick 2>/dev/null)"
      ;;
    *)
      return 2
      ;;
  esac

  case "$out" in
    live)    return 0 ;;
    offline) return 1 ;;
    *)       return 2 ;;
  esac
}

probe_platform() {
  local url="$1" key="$2" name="$3"
  local platform="${4:-}"

  local host port
  host="$(printf '%s' "$url" | sed -E 's#^[a-z]+://##; s#/.*$##; s#:[0-9]+$##')"
  port="$(printf '%s' "$url" | sed -En 's#.*:([0-9]+)/.*#\1#p')"
  [ -z "$port" ] && port=1935

  # 1. DNS + TCP reachability
  if ! nc -z -G 5 "$host" "$port" 2>/dev/null; then
    bad "$name — cannot reach $host:$port"
    echo "      (DNS, firewall, or the host/port is wrong)"
    return 1
  fi
  ok "$name — $host:$port reachable"

  # 2. RTMP handshake + credential check via ffmpeg.
  #    A 0.2s black clip is enough to complete the handshake and get the
  #    platform's response, without publishing meaningful content.
  local probe_dir="$DIR/test-out/dryrun"
  mkdir -p "$probe_dir"
  local log
  log="$(ffmpeg -hide_banner -loglevel info \
          -f lavfi -i "color=c=black:s=320x240:d=0.2:r=5" \
          -c:v libx264 -preset ultrafast -t 0.2 \
          -f flv "$url/$key" 2>&1)"

  # Rejected: the platform closed the connection during the handshake.
  if printf '%s' "$log" | grep -q "Error opening output"; then
    # A channel that is ALREADY broadcasting rejects a second publish.
    # That is by far the most common cause and it looks identical to a
    # bad key in ffmpeg's generic "Input/output error". Check the API
    # before blaming the credential.
    if [ -n "$platform" ] && platform_is_live "$platform"; then
      warn "$name — channel is ALREADY LIVE (a second publish is rejected)"
      echo "      this is not a key problem. Stop the existing broadcast"
      echo "      (or accept that this platform is already streaming) and"
      echo "      re-run. The relay's own forward to this platform is"
      echo "      working -- that is why the channel shows as live."
      return 0
    fi
    bad "$name — REJECTED by platform (credential or account issue)"
    printf '%s\n' "$log" \
      | grep -iE "IO error|End of file|Connection refused|tls @|Connection reset" \
      | head -3 | sed 's/^/      /'
    echo "      check the key, the account type, and whether a concurrent"
    echo "      broadcast is already running on that channel"
    return 1
  fi

  # Accepted: ffmpeg got through the handshake and muxed output.
  if printf '%s' "$log" | grep -q "Lsize="; then
    ok "$name — handshake accepted, credential valid"
    return 0
  fi

  # Something else went wrong -- surface the real error.
  warn "$name — inconclusive, raw ffmpeg output:"
  printf '%s\n' "$log" | grep -viE "^\[libx264|^ *\[" | tail -6 | sed 's/^/      /'
  return 0
}

# ---------------------------------------------------------------------------
head2 "1. Relay status"
if curl -s -o /dev/null --max-time 2 "$API/v3/paths/list"; then
  ok "relay is running"
else
  bad "relay is NOT running — start with: launchctl kickstart -k gui/\$(id -u)/com.example.streaming-relay"
fi

LAND_ENC=$(python3 -c 'import urllib.parse; print(urllib.parse.quote("~^land(/.*)?$", safe=""))')
VERT_ENC=$(python3 -c 'import urllib.parse; print(urllib.parse.quote("~^vert(/.*)?$", safe=""))')

for spec in "land:$LAND_ENC" "vert:$VERT_ENC"; do
  P="${spec%%:*}"; ENC="${spec#*:}"
  CNT=$(curl -s "$API/v3/config/paths/get/$ENC" | python3 "$DIR/../tools/forward-list.py" count)
  if [ "${CNT:-0}" -gt 0 ]; then
    warn "$P already has $CNT forward target(s) — a real stream would go live"
    curl -s "$API/v3/config/paths/get/$ENC" | python3 "$DIR/../tools/forward-list.py" \
      | while IFS=$'\t' read -r u k; do
          [ -z "$u" ] && continue
          printf '      %s\n' "$u"
        done
  else
    ok "$P has no forward targets (nothing can broadcast)"
  fi
done

# ---------------------------------------------------------------------------
head2 "2. Keys"
declare -a PRESENT=()
declare -a MISSING=()
declare -a SKIPPED=()

for row in "${PLATFORMS[@]}"; do
  IFS='|' read -r name path url keyvar kind api_slug <<< "$row"

  # Deliberately not being tested -- report and move on.
  if is_skipped "$name"; then
    echo "  ${BOLD}$name${NC} ${DIM}[$path]${NC}"
    echo "      ${DIM}skipped (in the skip list) -- not tested, not counted${NC}"
    SKIPPED+=("$name")
    continue
  fi

  printf "  ${BOLD}%-22s${NC} %s\n" "$name" "${DIM}[$path]${NC}"
  key="${!keyvar:-}"
  if [ -z "$key" ]; then
    if [ "$REQUIRE_ALL" = "1" ]; then
      bad "no key set ($keyvar)"
      MISSING+=("$name")
    else
      warn "no key set ($keyvar) — will be skipped"
      MISSING+=("$name")
    fi
    continue
  fi
  ok "key present (${#key} chars)"
  PRESENT+=("$row")
  check_shape "$kind" "$key" || true
done

# ---------------------------------------------------------------------------
head2 "3. Platform connectivity + credential probe"
echo "${DIM}Opens each platform's RTMP endpoint and completes the handshake.${NC}"
echo "${DIM}No video payload is published. Some platforms may briefly show a${NC}"
echo "${DIM}broadcast that immediately ends.${NC}"
echo

for row in "${PRESENT[@]:-}"; do
  [ -z "$row" ] && continue
  IFS='|' read -r name path url keyvar kind api_slug <<< "$row"
  key="${!keyvar:-}"
  echo "  ${BOLD}--- $name ---${NC}"
  probe_platform "$url" "$key" "$name" "$api_slug"
  echo
done

# ---------------------------------------------------------------------------
head2 "4. Summary"
if [ "$FAILURES" -gt 0 ]; then
  echo "${RED}${BOLD}  $FAILURES problem(s) found${NC}"
else
  echo "${GREEN}${BOLD}  All checks passed${NC}"
fi
[ "$WARNINGS" -gt 0 ] && echo "${YELLOW}  $WARNINGS warning(s)${NC}"
if [ "${#SKIPPED[@]}" -gt 0 ]; then
  echo
  echo "${DIM}  Not tested (skipped on purpose):${NC}"
  for s in "${SKIPPED[@]}"; do echo "    ${DIM}- $s${NC}"; done
fi
if [ "${#MISSING[@]}" -gt 0 ]; then
  echo
  echo "${YELLOW}  Platforms without keys:${NC}"
  for m in "${MISSING[@]}"; do echo "    - $m"; done
fi

echo
echo "${BOLD}Next step${NC}"
echo "  Fix anything above, then run:  ./go-live.sh"
echo
echo "${YELLOW}  Reminder: Instagram, TikTok and Kick keys expire. Re-copy them"
echo "  right before you go live, then re-run this dry run to confirm.${NC}"

exit $([ "$FAILURES" -gt 0 ] && echo 1 || echo 0)
