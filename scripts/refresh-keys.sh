#!/usr/bin/env bash
# =============================================================================
# refresh-keys.sh -- interactive key wizard
#
# The flow is PROBE FIRST, PROMPT SECOND:
#
#   1. Test every platform's current credential
#   2. Only the ones that FAIL get a prompt
#   3. Each new key is tested immediately -- you can retry without redoing
#      the whole run
#   4. Anything still failing at the end is listed with next steps
#
# Nothing is broadcast. Each test is an RTMP handshake that is closed before
# any video payload is sent.
#
# Usage:
#   ./refresh-keys.sh                 run the wizard
#   ./refresh-keys.sh --test-only     test only, don't prompt for anything
#   ./refresh-keys.sh --include-skipped  also test platforms in the skip list
# =============================================================================

set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KEYS_FILE="$DIR/../stream-keys.env"
API="http://127.0.0.1:9997"

GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; BLUE=$'\033[34m'
BOLD=$'\033[1m'; DIM=$'\033[2m'; NC=$'\033[0m'

TEST_ONLY=0
INCLUDE_SKIPPED=0
for a in "$@"; do
  case "$a" in
    --test-only) TEST_ONLY=1 ;;
    --include-skipped) INCLUDE_SKIPPED=1 ;;
  esac
done

info()  { echo "${GREEN}==>${NC} $*"; }
warn()  { echo "${YELLOW}  !${NC} $*"; }
err()   { echo "${RED}  ✗${NC} $*"; }
ok()    { echo "${GREEN}  ✓${NC} $*"; }
head2() { echo; echo "${BOLD}$1${NC}"; }

[ -f "$KEYS_FILE" ] || { echo "${RED}error:${NC} no $KEYS_FILE"; exit 1; }
# Parse the key file as data -- do not source it.
# shellcheck disable=SC1091
. "$DIR/../tools/load-env.sh" "$KEYS_FILE"

if ! curl -s -o /dev/null --max-time 2 "$API/v3/paths/list"; then
  echo "${RED}error:${NC} relay is not running."
  echo "  start it with: launchctl kickstart -k gui/\$(id -u)/com.example.streaming-relay"
  exit 1
fi

# ---------------------------------------------------------------------------
# Platform table
#   name|path|url|keyvar|urlvar|label
#   urlvar is the env var that holds the server URL ("" = fixed URL)
# ---------------------------------------------------------------------------
PLATFORMS=(
  "YouTube (landscape)|land|rtmps://a.rtmps.youtube.com:443/live2|YT_LAND_KEY||YouTube"
  "Twitch|land|rtmp://ingest.global-contribute.live-video.net/app|TWITCH_KEY||Twitch"
  "Kick|land|rtmps://fa723fc1b171.global-contribute.live-video.net/|KICK_KEY||Kick"
  "YouTube (portrait)|vert|rtmps://a.rtmps.youtube.com:443/live2|YT_VERT_KEY||YouTube"
  "TikTok|vert|${TIKTOK_URL:-rtmps://live.tiktokcdn.com/live}|TIKTOK_KEY|TIKTOK_URL|TikTok"
  "Instagram|vert|${IG_URL:-rtmps://live.instagram.com/rtmp}|IG_KEY|IG_URL|Instagram"
)

# ---------------------------------------------------------------------------
# The probe. Returns:
#   0 = accepted
#   1 = rejected (credential invalid / expired / spent)
#   2 = unreachable
#   3 = inconclusive
# ---------------------------------------------------------------------------
probe() {
  local url="$1" key="$2" log

  local host port
  host="$(printf '%s' "$url" | sed -E 's#^[a-z]+://##; s#/.*$##; s#:[0-9]+$##')"
  port="$(printf '%s' "$url" | sed -En 's#.*:([0-9]+)/.*#\1#p')"
  [ -z "$port" ] && port=1935

  if ! nc -z -G 5 "$host" "$port" 2>/dev/null; then
    PROBE_DETAIL="cannot reach $host:$port"
    return 2
  fi

  log="$(ffmpeg -hide_banner -loglevel info \
          -f lavfi -i "color=c=black:s=320x240:d=0.3:r=5" \
          -c:v libx264 -preset ultrafast -t 0.3 \
          -f flv "${url%/}/$key" 2>&1)"

  if printf '%s' "$log" | grep -q "Lsize="; then
    PROBE_DETAIL="handshake accepted"
    return 0
  fi

  if printf '%s' "$log" | grep -q "Error opening output"; then
    if printf '%s' "$log" | grep -qi "not permitted"; then
      PROBE_DETAIL="credential spent or expired (Operation not permitted)"
    elif printf '%s' "$log" | grep -qi "End of file"; then
      PROBE_DETAIL="credential rejected (connection closed during handshake)"
    else
      PROBE_DETAIL="rejected"
    fi
    return 1
  fi

  PROBE_DETAIL="inconclusive"
  return 3
}

# ---------------------------------------------------------------------------
# Where to get a fresh credential, per platform.
# ---------------------------------------------------------------------------
where_to_get() {
  case "$1" in
    "YouTube (landscape)")
      echo "YouTube Studio → Go Live → Stream settings → Stream key (landscape)"
      ;;
    "YouTube (portrait)")
      echo "YouTube Studio → Go Live → Stream settings → the PORTRAIT stream"
      echo "  (Create Stream → 'Portrait orientation' if you don't have one yet)"
      ;;
    "Twitch")
      echo "Twitch Creator Dashboard → Settings → Stream → Primary Stream Key"
      ;;
    "Kick")
      echo "Kick Creator Dashboard → Settings → Broadcasting → Stream Key"
      echo "  (copy the Server URL too — it can change)"
      ;;
    "TikTok")
      echo "TikTok app → Profile → Menu → TikTok Studio → LIVE"
      echo "  → LIVE Studio → 'Stream with software' → copy Server URL + Stream Key"
      ;;
    "Instagram")
      echo "Instagram app → Create → Live video → 'Stream with broadcast software'"
      echo "  → copy Stream URL + Stream key"
      ;;
    *)
      echo "(see GET-KEYS.md)"
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Update a key (and optionally its URL) in stream-keys.env, preserving
# comments and every other variable.
# ---------------------------------------------------------------------------
set_key() {
  local keyvar="$1" value="$2" urlvar="$3" urlvalue="$4"
  local tmp
  tmp="$(mktemp)"

  if [ -n "$urlvar" ] && [ -n "$urlvalue" ]; then
    # Replace both KEY and URL lines
    awk -v kv="$keyvar" -v v="$value" -v uv="$urlvar" -v uv_val="$urlvalue" '
      BEGIN { kvdone=0; uvdone=0 }
      $0 ~ "^" kv "=" { print kv "=\"" v "\""; kvdone=1; next }
      $0 ~ "^" uv "=" { print uv "=\"" uv_val "\""; uvdone=1; next }
      { print }
      END {
        if (!kvdone) print kv "=\"" v "\""
        if (!uvdone) print uv "=\"" uv_val "\""
      }' "$KEYS_FILE" > "$tmp"
  else
    awk -v kv="$keyvar" -v v="$value" '
      BEGIN { done=0 }
      $0 ~ "^" kv "=" { print kv "=\"" v "\""; done=1; next }
      { print }
      END { if (!done) print kv "=\"" v "\"" }' "$KEYS_FILE" > "$tmp"
  fi

  cat "$tmp" > "$KEYS_FILE"
  rm -f "$tmp"
  chmod 600 "$KEYS_FILE"
}

# ---------------------------------------------------------------------------
# Read the current value of a URL var
# ---------------------------------------------------------------------------
get_url() {
  local urlvar="$1" fallback="$2"
  [ -z "$urlvar" ] && { echo "$fallback"; return; }
  local v="${!urlvar:-}"
  [ -z "$v" ] && v="$fallback"
  echo "$v"
}

# ===========================================================================
echo "${BOLD}=== Stream key wizard ===${NC}"
echo "${DIM}Tests every credential first. Only the ones that fail get a prompt.${NC}"
echo "${DIM}Nothing is broadcast.${NC}"

# --- Phase 1: test everything ---------------------------------------------
head2 "Phase 1 — testing current credentials"
echo

declare -a WORKS=()
declare -a FAILED=()
declare -a SKIPPED_PLATS=()

for row in "${PLATFORMS[@]}"; do
  IFS='|' read -r name path url keyvar urlvar label <<< "$row"

  # Honour the skip list unless told otherwise
  if [ "$INCLUDE_SKIPPED" = "0" ]; then
    skip_hit=0
    for s in ${SKIP_LIST:-} ${SKIP_PLATFORMS:-}; do
      [ "$s" = "$name" ] && skip_hit=1
    done
    if [ "$skip_hit" = "1" ]; then
      printf "  %-22s ${DIM}skipped${NC}\n" "$name"
      SKIPPED_PLATS+=("$name")
      continue
    fi
  fi

  key="${!keyvar:-}"
  if [ -z "$key" ]; then
    printf "  %-22s ${YELLOW}no key set${NC}\n" "$name"
    FAILED+=("$row")
    continue
  fi

  printf "  %-22s " "$name"
  probe "$url" "$key"
  rc=$?
  case "$rc" in
    0) ok "$PROBE_DETAIL"; WORKS+=("$row") ;;
    1) err "$PROBE_DETAIL"; FAILED+=("$row") ;;
    2) err "$PROBE_DETAIL"; FAILED+=("$row") ;;
    *) warn "$PROBE_DETAIL"; FAILED+=("$row") ;;
  esac
done

# --- Phase 2: fix the broken ones -----------------------------------------
if [ "${#FAILED[@]}" -eq 0 ]; then
  head2 "Phase 2 — nothing to fix"
  echo
  ok "every tested platform is already accepting its credential"
  [ "${#SKIPPED_PLATS[@]}" -gt 0 ] && {
    echo
    echo "${DIM}  Not tested: ${SKIPPED_PLATS[*]}${NC}"
  }
  echo
  info "run ./go-live.sh when you're ready"
  exit 0
fi

head2 "Phase 2 — fixing ${#FAILED[@]} credential(s)"
echo

FIXED=0
STILL_BROKEN=()

for row in "${FAILED[@]}"; do
  IFS='|' read -r name path url keyvar urlvar label <<< "$row"

  echo "${BOLD}── $name ──${NC}"
  where_to_get "$name" | sed 's/^/  /'
  echo

  if [ "$TEST_ONLY" = "1" ]; then
    echo "  ${DIM}(--test-only: not prompting)${NC}"
    echo
    STILL_BROKEN+=("$name")
    continue
  fi

  attempts=0
  resolved=0
  while [ "$attempts" -lt 3 ] && [ "$resolved" -eq 0 ]; do
    attempts=$((attempts+1))

    # --- prompt for the KEY first (it's the primary input) ---
    echo "  ${DIM}Stream key (Enter to skip this platform):${NC}"
    printf "    > "
    read -r newkey
    if [ -z "${newkey:-}" ]; then
      echo "  ${DIM}(skipped — keeping the old value)${NC}"
      echo
      break
    fi

    # --- then the URL (only for platforms that have one) ---
    cur_url="$(get_url "$urlvar" "$url")"
    new_url="$cur_url"
    if [ -n "$urlvar" ]; then
      echo "  ${DIM}Server URL (Enter to keep the current one):${NC}"
      printf "    %s\n" "$cur_url"
      read -r inp
      if [ -n "${inp:-}" ]; then
        new_url="$inp"
      fi
    fi

    # --- save immediately so a crash doesn't lose it ---
    set_key "$keyvar" "$newkey" "$urlvar" "$new_url"

    # --- re-probe with the new value ---
    echo "  testing the new key..."
    probe "$new_url" "$newkey"
    rc=$?
    case "$rc" in
      0)
        ok "accepted — $name is good"
        resolved=1
        FIXED=$((FIXED+1))
        ;;
      1|2|3)
        err "$PROBE_DETAIL"
        echo "  ${DIM}  saved anyway. Try again, or press Enter to keep it${NC}"
        ;;
    esac
    echo
  done

  [ "$resolved" -eq 0 ] && STILL_BROKEN+=("$name")
  echo
done

# De-duplicate the still-broken list (a platform can be appended twice if the
# user skipped it mid-loop).
if [ "${#STILL_BROKEN[@]}" -gt 0 ]; then
  UNIQUE_BROKEN=()
  for b in "${STILL_BROKEN[@]}"; do
    seen=0
    for u in "${UNIQUE_BROKEN[@]:-}"; do
      [ "$u" = "$b" ] && seen=1
    done
    [ "$seen" = "0" ] && UNIQUE_BROKEN+=("$b")
  done
  STILL_BROKEN=("${UNIQUE_BROKEN[@]}")
fi

# --- Summary ---------------------------------------------------------------
head2 "Summary"
if [ "$FIXED" -gt 0 ]; then
  ok "$FIXED credential(s) refreshed and verified"
fi
if [ "${#WORKS[@]}" -gt 0 ]; then
  ok "${#WORKS[@]} credential(s) were already good"
fi
if [ "${#STILL_BROKEN[@]}" -gt 0 ]; then
  echo
  echo "${YELLOW}  Still needing attention:${NC}"
  for b in "${STILL_BROKEN[@]}"; do echo "    - $b"; done
  echo
  echo "  Each of these needs a key minted in a fresh session on the platform"
  echo "  itself. See GET-KEYS.md / GET-TIKTOK-KEYS.md."
fi
if [ "${#SKIPPED_PLATS[@]}" -gt 0 ]; then
  echo
  echo "${DIM}  Not tested: ${SKIPPED_PLATS[*]}${NC}"
  echo "${DIM}  (run with --include-skipped to test those too)${NC}"
fi

echo
if [ "${#STILL_BROKEN[@]}" -eq 0 ]; then
  echo "${GREEN}${BOLD}  All credentials verified${NC}"
  echo
  echo "  Next:  ./go-live.sh --all"
  exit 0
else
  echo "${YELLOW}${BOLD}  ${#STILL_BROKEN[@]} credential(s) still need attention${NC}"
  exit 1
fi
