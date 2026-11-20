#!/usr/bin/env bash
# =============================================================================
# test-relay.sh -- end-to-end verification of the local relay
#
# Publishes a synthetic LANDSCAPE stream and a synthetic PORTRAIT stream to
# MediaMTX, then reads each back and verifies:
#   1. the relay accepts both paths
#   2. the dimensions survive the round trip (1920x1080 and 1080x1920)
#   3. HLS preview is serving for both
#   4. forward targets register, and key rotation replaces in place
#
# Uses ffmpeg's testsrc2 so orientation is visually obvious.
# Nothing here touches OBS, real stream keys, or any platform.
# =============================================================================

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API="http://127.0.0.1:9997"
OUT="$DIR/test-out"
TOOLS="$DIR/tools"
mkdir -p "$OUT"

GREEN=$'\033[32m'; RED=$'\033[31m'; BOLD=$'\033[1m'; NC=$'\033[0m'
FAILED=0
pass() { echo "${GREEN}  PASS${NC} $*"; }
fail() { echo "${RED}  FAIL${NC} $*"; FAILED=1; }

echo "${BOLD}=== Local relay end-to-end test ===${NC}"
echo

command -v ffmpeg >/dev/null 2>&1 || { echo "${RED}ffmpeg not found${NC}"; exit 1; }
if ! curl -s -o /dev/null --max-time 2 "$API/v3/paths/list"; then
  echo "${RED}MediaMTX API not reachable -- is the service loaded?${NC}"; exit 1
fi
echo "${GREEN}preflight ok${NC} (ffmpeg present, MediaMTX API up)"
echo

LAND_PID=""; VERT_PID=""
cleanup() { [ -n "${1:-}" ] && kill "$1" 2>/dev/null; return 0; }
trap 'cleanup "$LAND_PID"; cleanup "$VERT_PID"' EXIT

echo "${BOLD}1. Publishing LANDSCAPE (1920x1080) -> rtmp://127.0.0.1:1935/land/land${NC}"
# NOTE: Aitum builds the publish URL as server + "/" + stream_key, so a
# server of .../land with key "land" lands on the runtime path "land/land".
# We publish to the same shape so the test exercises the real wiring.
ffmpeg -hide_banner -loglevel error -re \
  -f lavfi -i "testsrc2=size=1920x1080:rate=30" \
  -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p \
  -g 60 -c:a aac -b:a 128k \
  -f flv "rtmp://127.0.0.1:1935/land/land" > "$OUT/land.log" 2>&1 &
LAND_PID=$!

echo "${BOLD}2. Publishing PORTRAIT (1080x1920) -> rtmp://127.0.0.1:1935/vert/vert${NC}"
ffmpeg -hide_banner -loglevel error -re \
  -f lavfi -i "testsrc2=size=1080x1920:rate=30" \
  -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p \
  -g 60 -c:a aac -b:a 128k \
  -f flv "rtmp://127.0.0.1:1935/vert/vert" > "$OUT/vert.log" 2>&1 &
VERT_PID=$!

echo
echo "  waiting for both paths to become ready..."
for _ in $(seq 1 60); do
  READY=$(curl -s "$API/v3/paths/list" | python3 "$TOOLS/dump-paths.py" | grep -c "ready=True")
  [ "$READY" = "2" ] && break
  sleep 0.5
done

echo
echo "${BOLD}3. Path state${NC}"
curl -s "$API/v3/paths/list" | python3 "$TOOLS/dump-paths.py"

echo
echo "${BOLD}4. Dimension check${NC}"
for spec in "land 1920x1080" "vert 1080x1920"; do
  set -- $spec
  P=$1; EXP=$2
  GOT=$(curl -s "$API/v3/paths/list" | python3 "$TOOLS/path-dims.py" "$P")
  if [ "$GOT" = "$EXP" ]; then
    pass "$P is $GOT (expected $EXP)"
  elif [ -n "$GOT" ]; then
    fail "$P is $GOT, expected $EXP"
  else
    fail "$P reported no video dimensions"
  fi
done

echo
echo "${BOLD}5. HLS preview${NC}"
# MediaMTX 302-redirects the first hit and sets a "Secure; HttpOnly" cookie.
# Browsers refuse to store a Secure cookie over plain http://, so browsing
# the bare URL lands back on the same URL WITHOUT the cookie and MediaMTX
# answers {"error":"no stream is available on path ..."} even though the
# stream is live. ?cookieCheck=1 in the URL satisfies the check directly.
# We test BOTH forms: the ?cookieCheck=1 form must serve a real playlist,
# and the bare form must at least redirect (not 404).
for spec in "land:land/land" "vert:vert/vert"; do
  P="${spec%%:*}"; RP="${spec#*:}"
  BODY=$(curl -s -L -c "$OUT/cookies.txt" -b "$OUT/cookies.txt" \
              --max-time 8 "http://127.0.0.1:8888/$RP/index.m3u8?cookieCheck=1")
  if printf '%s' "$BODY" | grep -q "#EXTM3U"; then
    pass "HLS $P serving playlist (http://127.0.0.1:8888/$RP/index.m3u8?cookieCheck=1)"
  else
    fail "HLS $P did not serve a playlist (got: $(printf '%s' "$BODY" | head -c 80))"
  fi

  CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 \
              "http://127.0.0.1:8888/$RP/index.m3u8")
  if [ "$CODE" = "302" ]; then
    pass "HLS $P bare URL redirects for cookie check (302)"
  else
    fail "HLS $P bare URL expected 302, got $CODE"
  fi
done

echo
echo "${BOLD}6. Forward targets + key rotation${NC}"
LAND_ENC=$(python3 -c 'import urllib.parse; print(urllib.parse.quote("~^land(/.*)?$", safe=""))')
VERT_ENC=$(python3 -c 'import urllib.parse; print(urllib.parse.quote("~^vert(/.*)?$", safe=""))')
"$DIR/relay.sh" add-forward land "rtmp://127.0.0.1:1935/sink-land" "DUMMY" >/dev/null 2>&1
"$DIR/relay.sh" add-forward vert "rtmp://127.0.0.1:1935/sink-vert" "DUMMY" >/dev/null 2>&1
CNT=$(curl -s "$API/v3/config/paths/get/$VERT_ENC" | python3 "$TOOLS/forward-list.py" count)
if [ "${CNT:-0}" -ge 1 ]; then
  pass "forward target registered on vert (count=$CNT)"

  "$DIR/relay.sh" add-forward vert "rtmp://127.0.0.1:1935/sink-vert" "DUMMY2" >/dev/null 2>&1
  CNT2=$(curl -s "$API/v3/config/paths/get/$VERT_ENC" | python3 "$TOOLS/forward-list.py" count)
  KEY=$(curl -s "$API/v3/config/paths/get/$VERT_ENC" | python3 "$TOOLS/forward-list.py" | grep "sink-vert" | cut -f2)
  if [ "${CNT2:-0}" = "1" ] && [ "$KEY" = "DUMMY2" ]; then
    pass "key rotation replaced in place (1 target, new key live, no duplicate)"
  else
    fail "key rotation gave count=$CNT2 key=$KEY, expected count=1 key=DUMMY2"
  fi
else
  fail "could not register a forward target on vert"
fi

echo
echo "${BOLD}7. Cleanup${NC}"
cleanup "$LAND_PID"; cleanup "$VERT_PID"
"$DIR/relay.sh" remove-forward land "rtmp://127.0.0.1:1935/sink-land" >/dev/null 2>&1
"$DIR/relay.sh" remove-forward vert "rtmp://127.0.0.1:1935/sink-vert" >/dev/null 2>&1
echo "  stopped test publishers, removed test forward targets"

echo
if [ "$FAILED" = "0" ]; then
  echo "${GREEN}${BOLD}=== ALL CHECKS PASSED ===${NC}"
else
  echo "${RED}${BOLD}=== SOME CHECKS FAILED ===${NC}"
fi
exit "$FAILED"
