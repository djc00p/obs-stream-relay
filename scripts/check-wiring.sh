#!/usr/bin/env bash
# =============================================================================
# check-wiring.sh -- verify the Aitum -> relay wiring is correct
#
# Checks the three things that silently break a multistream:
#   1. each relay path carries the EXPECTED dimensions
#      (land = 1920x1080, vert = 1080x1920)
#   2. each relay path has at least one forward target configured
#   3. there is no EXTRA live publisher beyond the expected land/vert pair
#
# Read-only. Touches nothing.
# =============================================================================

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API="http://127.0.0.1:9997"
TOOLS="$DIR/tools"

GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; NC=$'\033[0m'
FAILED=0
pass() { echo "${GREEN}  ✓${NC} $*"; }
fail() { echo "${RED}  ✗${NC} $*"; FAILED=1; }
warn() { echo "${YELLOW}  !${NC} $*"; }

echo "${BOLD}=== Aitum → relay wiring check ===${NC}"
echo

if ! curl -s -o /dev/null --max-time 2 "$API/v3/paths/list"; then
  echo "${RED}relay not running${NC}"
  echo "  start it with: launchctl kickstart -k gui/\$(id -u)/com.example.streaming-relay"
  exit 1
fi

echo "${BOLD}1. Path dimensions${NC}"
for spec in "land 1920x1080 landscape" "vert 1080x1920 portrait"; do
  set -- $spec
  P=$1; EXP=$2; LABEL=$3
  GOT=$(curl -s "$API/v3/paths/list" | python3 "$TOOLS/path-dims.py" "$P")
  LIVE=$(curl -s "$API/v3/paths/list" | python3 "$TOOLS/path-dims.py" --name "$P")
  if [ -z "$GOT" ]; then
    fail "$P — no video yet. Is OBS publishing to rtmp://127.0.0.1:1935/$P ?"
    echo "      ${YELLOW}Live paths on the relay right now:${NC}"
    curl -s "$API/v3/paths/list" | python3 "$TOOLS/path-dims.py" \
      | while IFS=$'\t' read -r n g; do
          [ -z "$n" ] && continue
          printf '        %-16s %s\n' "$n" "$g"
        done
    [ -z "$LIVE" ] && echo "        ${YELLOW}(none — nothing is publishing)${NC}"
  elif [ "$GOT" = "$EXP" ]; then
    pass "$P is $GOT ($LABEL) — correct${LIVE:+ [path: $LIVE]}"
  else
    fail "$P is $GOT, expected $EXP ($LABEL)"
    echo "      ${YELLOW}If the orientation is swapped, check the Canvas dropdown"
    echo "      on that Aitum output.${NC}"
  fi
done

echo
echo "${BOLD}2. Forward targets${NC}"
LAND_ENC=$(python3 -c 'import urllib.parse; print(urllib.parse.quote("~^land(/.*)?$", safe=""))')
VERT_ENC=$(python3 -c 'import urllib.parse; print(urllib.parse.quote("~^vert(/.*)?$", safe=""))')
for spec in "land:$LAND_ENC" "vert:$VERT_ENC"; do
  P="${spec%%:*}"; ENC="${spec#*:}"
  CNT=$(curl -s "$API/v3/config/paths/get/$ENC" | python3 "$TOOLS/forward-list.py" count)
  if [ "${CNT:-0}" -gt 0 ]; then
    pass "$P has $CNT forward target(s)"
    curl -s "$API/v3/config/paths/get/$ENC" | python3 "$TOOLS/forward-list.py" \
      | while IFS=$'\t' read -r u k; do
          [ -z "$u" ] && continue
          printf '      %s  key=%s\n' "$u" "${k:0:10}***"
        done
  else
    warn "$P has no forward targets yet — run ./go-live.sh before streaming"
  fi
done

echo
echo "${BOLD}3. Unexpected publishers${NC}"
# The relay should carry exactly two publishers: land/land and vert/vert.
# OBS plugins can publish on their own without being an Aitum output. We
# found the "vertical-canvas" plugin running its own "restream alt output"
# at rtmp://127.0.0.1:1935/vertical, which lands on the runtime path
# "vertical/land" with no forward targets -- a live publisher whose stream
# goes nowhere, burning encoder headroom and putting a duplicate copy of the
# portrait feed on the wire.
#
# Flag any path that is not land*/vert*.
EXTRA="$(bash "$TOOLS/check-unexpected-paths.sh" 2>/dev/null)"
if [ -z "$EXTRA" ]; then
  pass "only the expected land/vert publishers are live"
else
  fail "$(( $(printf '%s\n' "$EXTRA" | wc -l | tr -d ' ') )) extra publisher(s) on the relay:"
  printf '%s\n' "$EXTRA" | while IFS=$'\t' read -r n g; do
    [ -z "$n" ] && continue
    printf '        %-16s %s\n' "$n" "${g:-no-video}"
  done
  echo
  echo "      ${YELLOW}These are publishers nobody is forwarding. They waste encoder${NC}"
  echo "      ${YELLOW}headroom and duplicate your feed on the wire.${NC}"
  echo
  echo "      ${YELLOW}Known case: the 'vertical-canvas' OBS plugin runs its own${NC}"
  echo "      ${YELLOW}'restream alt output' at rtmp://127.0.0.1:1935/vertical.${NC}"
  echo "      ${YELLOW}Fix it in OBS: Vertical Canvas -> Stream -> clear the alt${NC}"
  echo "      ${YELLOW}output server/key (it is kept in plugin runtime state, not${NC}"
  echo "      ${YELLOW}in plugin_config/vertical-canvas/config.json, so it can only${NC}"
  echo "      ${YELLOW}be changed from the OBS UI).${NC}"
  echo
  echo "      ${YELLOW}Aitum's own outputs are fine -- start them from the Aitum dock.${NC}"
fi

echo
echo "${BOLD}4. Preview URLs${NC}"
# The runtime path is server + "/" + stream_key (Aitum appends the key as a
# path segment), so the HLS muxers are "land/land" and "vert/vert".
#
# The ?cookieCheck=1 query is REQUIRED when browsing over plain http://.
# MediaMTX 302-redirects the first hit and sets a "Secure; HttpOnly" cookie.
# Browsers refuse to store a Secure cookie over http://, so the redirect
# loops back to the same URL without it and MediaMTX answers with
# {"error":"no stream is available on path '...'"} even though the stream is
# live. Passing ?cookieCheck=1 in the URL satisfies the check directly.
echo "  PLAYER (recommended) : http://127.0.0.1:8899/"
echo "    two streams side by side, live dimensions, no file-download prompt"
echo
echo "  raw playlist (landscape) : http://127.0.0.1:8888/land/land/index.m3u8?cookieCheck=1"
echo "  raw playlist (portrait)  : http://127.0.0.1:8888/vert/vert/index.m3u8?cookieCheck=1"
echo
echo "  NOTE: the ?cookieCheck=1 query is REQUIRED over http://."
echo "  MediaMTX sets a 'Secure; HttpOnly' cookie and browsers refuse to store a"
echo "  Secure cookie over plain http, so the bare URL redirects back to itself"
echo "  without the cookie and shows 'no stream is available' even when live."
echo "  Safari also offers to DOWNLOAD a bare .m3u8 instead of playing it --"
echo "  use the player URL above for viewing."
echo
echo "  start the player with: launchctl kickstart -k gui/\$(id -u)/com.example.relay-preview"

echo
if [ "$FAILED" = "0" ]; then
  echo "${GREEN}${BOLD}=== WIRING OK ===${NC}"
else
  echo "${RED}${BOLD}=== WIRING PROBLEM ===${NC}"
fi
exit "$FAILED"
