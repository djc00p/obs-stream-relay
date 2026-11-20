#!/usr/bin/env bash
# =============================================================================
# go-live.sh -- prepare the relay for a stream session
#
# Sets up the forward targets for both paths. Prompts for keys it doesn't
# have, skips platforms you don't want, and prints the exact OBS settings.
#
# Keys are read from a local, gitignored file so you don't retype them:
#   ~/Streaming-Relay/stream-keys.env
#
# Usage:
#   ./go-live.sh              interactive, asks what you're streaming to
#   ./go-live.sh --dry-run    show what would be configured, change nothing
#   ./go-live.sh --all        use every platform that has a key
# =============================================================================

set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API="http://127.0.0.1:9997"
KEYS_FILE="$DIR/../stream-keys.env"

GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; DIM=$'\033[2m'; NC=$'\033[0m'
DRY=0
ALL=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --all) ALL=1 ;;
  esac
done

info()  { echo "${GREEN}==>${NC} $*"; }
warn()  { echo "${YELLOW}warn:${NC} $*" >&2; }
die()   { echo "${RED}error:${NC} $*" >&2; exit 1; }
ask()   { local p="$1" d="$2" v; printf "%s [%s]: " "$p" "$d"; read -r v; echo "${v:-$d}"; }

if ! curl -s -o /dev/null --max-time 2 "$API/v3/paths/list"; then
  die "relay is not running. Start it with:  launchctl kickstart -k gui/\$(id -u)/com.example.streaming-relay"
fi

# Load saved keys if present. NOT sourced -- the loader parses the
# file as data instead of running it as shell.
if [ -f "$KEYS_FILE" ]; then
  # shellcheck disable=SC1091
  . "$DIR/../tools/load-env.sh" "$KEYS_FILE"
fi

# --- platform table (kept in sync with dry-run.sh) -------------------------
# name|path|url|keyvar
PLATFORMS=(
  "YouTube (landscape)|land|rtmps://a.rtmps.youtube.com:443/live2|YT_LAND_KEY"
  "Twitch|land|rtmp://ingest.global-contribute.live-video.net/app|TWITCH_KEY"
  "Kick|land|rtmps://fa723fc1b171.global-contribute.live-video.net/|KICK_KEY"
  "YouTube (portrait)|vert|rtmps://a.rtmps.youtube.com:443/live2|YT_VERT_KEY"
  "TikTok|vert|${TIKTOK_URL:-rtmps://live.tiktokcdn.com/live}|TIKTOK_KEY"
  "Instagram|vert|${IG_URL:-rtmps://live.instagram.com/rtmp}|IG_KEY"
)

echo "${BOLD}=== Relay go-live setup ===${NC}"
echo
echo "${DIM}Platform keys live in: $KEYS_FILE${NC}"
echo

declare -a LAND_TARGETS=()
declare -a VERT_TARGETS=()

add_target() {
  local name="$1" path="$2" url="$3" keyvar="$4"
  local key="${!keyvar:-}"

  # Respect the skip list -- a skipped platform is not added at all.
  # Both names are honored: refresh-keys.sh writes SKIP_PLATFORMS, but older
  # hand-edited files used SKIP_LIST. Reading only one of them silently
  # ignored the skip and tried to publish to a platform you said to skip.
  local s
  for s in ${SKIP_LIST:-} ${SKIP_PLATFORMS:-}; do
    if [ "$s" = "$name" ]; then
      echo "  ${DIM}$name skipped (skip list) -- not being streamed to${NC}"
      return
    fi
  done

  if [ -z "$key" ]; then
    if [ "$ALL" = "1" ]; then
      echo "  ${DIM}$name skipped (no $keyvar)${NC}"
      return
    fi
    key=$(ask "  $name stream key" "(skip to omit)")
  fi
  [ -z "$key" ] && { echo "  ${DIM}$name skipped${NC}"; return; }
  if [ "$path" = "land" ]; then
    LAND_TARGETS+=("$name|$url|$key")
  else
    VERT_TARGETS+=("$name|$url|$key")
  fi
}

echo "${BOLD}LANDSCAPE path (1920x1080)${NC}"
for row in "${PLATFORMS[@]}"; do
  IFS='|' read -r n p u kv <<< "$row"
  [ "$p" = "land" ] && add_target "$n" "$p" "$u" "$kv"
done

echo
echo "${BOLD}PORTRAIT path (1080x1920)${NC}"
for row in "${PLATFORMS[@]}"; do
  IFS='|' read -r n p u kv <<< "$row"
  [ "$p" = "vert" ] && add_target "$n" "$p" "$u" "$kv"
done

echo
echo "${BOLD}Plan${NC}"
for t in "${LAND_TARGETS[@]:-}"; do [ -n "$t" ] && echo "  land  ${t%%|*}"; done
for t in "${VERT_TARGETS[@]:-}"; do [ -n "$t" ] && echo "  vert  ${t%%|*}"; done

if [ "$DRY" = "1" ]; then
  echo
  echo "${YELLOW}dry run -- nothing was changed${NC}"
  echo
  echo "  To validate the credentials for real (without broadcasting), run:"
  echo "    ./dry-run.sh"
  exit 0
fi

echo
info "applying forward targets..."

# Clear existing forwards first so stale platforms don't linger.
# Path names are regexes (leading "~" = regex path in MediaMTX) and must be
# URL-encoded when used in the API.
enc() { python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }
LAND_ENC="$(enc '~^land(/.*)?$')"
VERT_ENC="$(enc '~^vert(/.*)?$')"

for pair in "$LAND_ENC" "$VERT_ENC"; do
  curl -s -X PATCH "$API/v3/config/paths/patch/$pair" \
       -H 'Content-Type: application/json' \
       -d '{"forward":[]}' > /dev/null
done

for t in "${LAND_TARGETS[@]:-}"; do
  [ -z "$t" ] && continue
  name="${t%%|*}"; rest="${t#*|}"; url="${rest%%|*}"; key="${rest#*|}"
  "$DIR/relay.sh" add-forward land "$url" "$key" > /dev/null 2>&1 \
    && echo "  ${GREEN}✓${NC} land  → $name" \
    || echo "  ${RED}✗${NC} land  → $name (failed)"
done

for t in "${VERT_TARGETS[@]:-}"; do
  [ -z "$t" ] && continue
  name="${t%%|*}"; rest="${t#*|}"; url="${rest%%|*}"; key="${rest#*|}"
  "$DIR/relay.sh" add-forward vert "$url" "$key" > /dev/null 2>&1 \
    && echo "  ${GREEN}✓${NC} vert  → $name" \
    || echo "  ${RED}✗${NC} vert  → $name (failed)"
done

echo
echo "${BOLD}OBS settings${NC}"
cat <<EOF
  Landscape output (Aitum or OBS Stream):
    Server : rtmp://127.0.0.1:1935/land
    Key    : (anything)

  Portrait output (Aitum Vertical / vertical-canvas):
    Server : rtmp://127.0.0.1:1935/vert
    Key    : (anything)

  Preview both in a browser:
    http://127.0.0.1:8899/

${BOLD}  Kick reminder${NC}
  Multistream toggle MUST be ON (you are streaming to horizontal platforms).
  Turn it on in the Kick dashboard once live, or type  /multi on  in chat.
  Recheck after changing stream category -- categories can reset it.

${BOLD}  Rotating a key mid-stream (TikTok / Instagram)${NC}
  ./relay.sh add-forward vert "<url>" "<new key>"
  Same URL = key replaced in place. The stream does not restart.
EOF

echo
"$DIR/relay.sh" status

# --- verify the forwards actually landed -----------------------------------
# relay.sh status prints the targets, but a silent failure (API refused, bad
# path name, typo) would leave you with zero forwards and no signal that
# nothing is going out. Read the API back and fail loudly.
echo
VERIFY="$(curl -s --max-time 3 "$API/v3/config/paths/list")"
LAND_N="$(printf '%s' "$VERIFY" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print(0); raise SystemExit
print(sum(len(it.get("forward") or []) for it in d.get("items",[]) if "land" in (it.get("name") or "")))
' 2>/dev/null)"
VERT_N="$(printf '%s' "$VERIFY" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print(0); raise SystemExit
print(sum(len(it.get("forward") or []) for it in d.get("items",[]) if "vert" in (it.get("name") or "")))
' 2>/dev/null)"

if [ "${LAND_N:-0}" -eq 0 ] && [ "${VERT_N:-0}" -eq 0 ]; then
  echo "${RED}================================================${NC}"
  echo "${RED} NO FORWARDS ARE CONFIGURED.${NC}"
  echo "${RED} Nothing is being published to any platform.${NC}"
  echo "${RED}================================================${NC}"
  echo "  Your keys live in: $KEYS_FILE"
  echo "  Run ${BOLD}./refresh-keys.sh${NC} to (re)validate and save keys,"
  echo "  then ${BOLD}./go-live.sh --all${NC} again."
  echo
  exit 1
fi

echo "${GREEN}✓ forwards live:${NC} land=${LAND_N:-0}  vert=${VERT_N:-0}"
echo "  (each forward is a separate connection to one platform)"
echo

# Warn about extra publishers. These are OBS plugins publishing to the relay
# on their own -- not Aitum outputs. They have no forwards, so their stream
# goes nowhere, but they still burn encoder headroom and put a duplicate copy
# of your feed on the wire.
EXTRA="$(bash "$DIR/../tools/check-unexpected-paths.sh" 2>/dev/null)"
if [ -n "$EXTRA" ]; then
  echo "${YELLOW}! extra publisher(s) on the relay:${NC}"
  printf '%s\n' "$EXTRA" | while IFS=$'\t' read -r n g; do
    [ -z "$n" ] && continue
    printf '    %-16s %s\n' "$n" "${g:-no-video}"
  done
  echo "  ${DIM}Nothing is forwarding these. If it is the 'vertical-canvas' plugin's${NC}"
  echo "  ${DIM}alt output, clear it in OBS: Vertical Canvas -> Stream.${NC}"
  echo
fi
