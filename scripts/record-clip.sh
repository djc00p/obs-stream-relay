#!/usr/bin/env bash
# =============================================================================
# record-clip.sh -- record a short clip from the relay's HLS output
#
# Records from the RELAY (not from OBS), so what you capture is exactly what
# the relay is forwarding -- the same bytes a platform would receive.
#
# Usage:
#   ./record-clip.sh                    # record both land and vert, 10s
#   ./record-clip.sh land               # landscape only
#   ./record-clip.sh vert               # portrait only
#   ./record-clip.sh land 20            # 20 seconds
#
# Output: ~/Movies/Relay-Clips/<timestamp>-<path>.mp4
# =============================================================================

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API="http://127.0.0.1:9997"
RELAY_HLS="http://127.0.0.1:8888"
OUT_DIR="$HOME/Movies/Relay-Clips"

WHICH="${1:-both}"
SECONDS_TO_RECORD="${2:-10}"

mkdir -p "$OUT_DIR"

GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; NC=$'\033[0m'
info() { echo "${GREEN}==>${NC} $*"; }
warn() { echo "${YELLOW}  !${NC} $*"; }
die()  { echo "${RED}✗${NC} $*" >&2; exit 1; }

# --- resolve the live runtime path names -----------------------------------
resolve_path() {
  local base="$1"
  curl -s --max-time 5 "$API/v3/paths/list" \
    | python3 "$DIR/../tools/resolve-one-path.py" "$base"
}

record_one() {
  local base="$1"
  local runtime_path
  runtime_path="$(resolve_path "$base")"

  if [ -z "$runtime_path" ]; then
    warn "$base is not publishing — skipping"
    return 1
  fi

  local stamp out
  stamp="$(date +%Y%m%d-%H%M%S)"
  out="$OUT_DIR/${stamp}-${base}.mp4"

  # ?cookieCheck=1 is required: MediaMTX's HLS cookie check uses a Secure
  # cookie, which is not stored over plain http://.
  local src="$RELAY_HLS/${runtime_path}/index.m3u8?cookieCheck=1"

  info "recording $base (${runtime_path}) for ${SECONDS_TO_RECORD}s"
  echo "      source: $src"
  echo "      output: $out"

  # -t before -i would cut on input timestamps; -t after -i is right for a
  # live stream. We copy video/audio (no re-encode) so it is fast and lossless.
  if ffmpeg -hide_banner -loglevel error -stats \
        -i "$src" \
        -t "$SECONDS_TO_RECORD" \
        -c copy -movflags +faststart \
        "$out" 2>"$DIR/test-out/record-$base.log"; then
    if [ -s "$out" ]; then
      local sz
      sz=$(du -h "$out" | cut -f1)
      echo "${GREEN}  ✓${NC} saved $out ($sz)"
      return 0
    fi
  fi

  warn "recording failed for $base — log:"
  tail -5 "$DIR/test-out/record-$base.log" 2>/dev/null | sed 's/^/      /'
  rm -f "$out"
  return 1
}

echo "${BOLD}=== Relay clip recorder ===${NC}"
echo

case "$WHICH" in
  land) record_one land ;;
  vert) record_one vert ;;
  both)
    record_one land
    echo
    record_one vert
    ;;
  *)
    die "usage: $0 [land|vert|both] [seconds]"
    ;;
esac

echo
info "clips directory: $OUT_DIR"
ls -1t "$OUT_DIR" 2>/dev/null | head -5 | sed 's/^/      /'
