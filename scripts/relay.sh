#!/usr/bin/env bash
# =============================================================================
# relay.sh -- manage MediaMTX forward targets at runtime
#
# TikTok and Instagram issue session-unique RTMP keys that expire. This script
# updates the live relay's forward list WITHOUT restarting the stream or
# dropping OBS's connection.
#
# Usage:
#   ./relay.sh start                 start MediaMTX (background)
#   ./relay.sh stop                  stop MediaMTX
#   ./relay.sh status                 show server + active paths + forwards
#   ./relay.sh list                   list forward targets per path
#   ./relay.sh add-forward <path> <url> <key>
#                                   add or replace a forward target
#   ./relay.sh remove-forward <path> <url>
#                                   remove a forward target by URL
#   ./relay.sh add <path> <url> <key>   alias for add-forward
#
# Examples:
#   ./relay.sh add-forward vert "rtmps://live.tiktokcdn.com/live" "abc123"
#   ./relay.sh add-forward vert "rtmps://live.tiktokcdn.com/live" "def456"   # replace same URL
#
# Notes:
#   - A forward target is identified by its URL. Re-adding the same URL with a
#     new key replaces the key in place (the stream is NOT interrupted).
#   - All-chat / OBS are unaffected by these changes.
# =============================================================================

set -euo pipefail

API="http://127.0.0.1:9997"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$DIR/mediamtx"
CFG="$DIR/../mediamtx.yml"
PIDFILE="$DIR/mediamtx.pid"
LOGFILE="$DIR/mediamtx.log"

# The relay's paths are REGULAR EXPRESSIONS (a leading "~" marks a regex path in
# MediaMTX). Aitum appends the stream key as a path segment, so a server of
# rtmp://127.0.0.1:1935/land with key "land" publishes to path "land/land".
# These regexes match land, land/land, land/anything.
#
#   land -> ~^land(/.*)?$
#   vert -> ~^vert(/.*)?$
#
# The API takes these names URL-encoded.
LAND_PATH='~^land(/.*)?$'
VERT_PATH='~^vert(/.*)?$'
enc() { python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }
LAND_ENC="$(enc "$LAND_PATH")"
VERT_ENC="$(enc "$VERT_PATH")"

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; NC=$'\033[0m'

die() { echo "${RED}error:${NC} $*" >&2; exit 1; }
info() { echo "${GREEN}==>${NC} $*"; }
warn() { echo "${YELLOW}warn:${NC} $*" >&2; }

api_up() {
  curl -s -o /dev/null --max-time 2 "$API/v3/paths/list" 2>/dev/null
}

require_api() {
  api_up || die "MediaMTX API not reachable at $API -- run './relay.sh start' first"
}

# --- read current forward list for a path (tab-separated: dest<TAB>key) ------
# MediaMTX stores a forward target as {"dest": "<url>#<streamKey>"} -- the
# stream key is a URL FRAGMENT, and the API field is "dest" (not "url").
# We split it back apart so keys can be read and replaced individually.
get_forwards() {
  local enc="$1"
  curl -s --max-time 5 "$API/v3/config/paths/get/$enc" \
    | python3 -c '
import json,sys
d=json.load(sys.stdin)
for f in (d.get("forward") or []):
    dest=f.get("dest") or ""
    url,_,frag=dest.partition("#")
    print(f"{url}\t{frag}")
' 2>/dev/null || true
}

# --- write a forward list for a path (stdin: url<TAB>key per line) ----------
# Reassembles each target as "<url>#<key>".
set_forwards() {
  local enc="$1"
  python3 -c '
import json,sys
enc=sys.argv[1]
fwd=[]
for line in sys.stdin:
    line=line.rstrip("\n")
    if not line.strip():
        continue
    url,_,key=line.partition("\t")
    dest=url + ("#"+key if key else "")
    fwd.append({"dest":dest})
print(json.dumps({"forward":fwd}))
' "$enc" | curl -s --max-time 5 -X PATCH "$API/v3/config/paths/patch/$enc" \
      -H 'Content-Type: application/json' -d @- > /dev/null
}

cmd_start() {
  if api_up; then
    info "MediaMTX already running"
    return 0
  fi
  info "starting MediaMTX..."
  cd "$DIR"
  nohup "$BIN" "$CFG" > "$LOGFILE" 2>&1 &
  echo $! > "$PIDFILE"
  for _ in $(seq 1 30); do
    if api_up; then
      info "MediaMTX up (pid $(cat "$PIDFILE"))"
      info "  RTMP ingest : rtmp://127.0.0.1:1935"
      info "  Control API : $API"
      info "  HLS preview : http://127.0.0.1:8888"
      info "  log         : $LOGFILE"
      return 0
    fi
    sleep 0.3
  done
  warn "MediaMTX did not come up in 9s. Last log lines:"
  tail -20 "$LOGFILE" >&2
  exit 1
}

cmd_stop() {
  if [ -f "$PIDFILE" ]; then
    local pid; pid="$(cat "$PIDFILE")"
    if kill -0 "$pid" 2>/dev/null; then
      info "stopping MediaMTX (pid $pid)..."
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PIDFILE"
    info "stopped"
  else
    info "not running (no pidfile)"
  fi
}

cmd_status() {
  if ! api_up; then
    warn "MediaMTX not running"
    exit 1
  fi
  info "MediaMTX is up"
  echo
  echo "${BOLD}Active paths:${NC}"
  curl -s "$API/v3/paths/list" | python3 "$DIR/../tools/dump-paths.py" 2>/dev/null || true
  echo
  echo "${BOLD}Forward targets:${NC}"
  for spec in "land:$LAND_ENC" "vert:$VERT_ENC"; do
    p="${spec%%:*}"; enc="${spec#*:}"
    local_fw="$(get_forwards "$enc")"
    if [ -z "$local_fw" ]; then
      echo "  $p: (none)"
    else
      echo "$local_fw" | while IFS=$'\t' read -r u k; do
        [ -z "$u" ] && continue
        printf '  %-12s %s  key=%s\n' "$p" "$u" "${k:0:8}***"
      done
    fi
  done
}

cmd_list() { cmd_status; }

cmd_add_forward() {
  local path="$1" url="$2" key="${3:-}"
  [ -n "$path" ] && [ -n "$url" ] || die "usage: $0 add-forward <path> <url> [key]"
  require_api

  local enc
  case "$path" in
    land) enc="$LAND_ENC" ;;
    vert) enc="$VERT_ENC" ;;
    *)   die "unknown path '$path' (use 'land' or 'vert')" ;;
  esac

  local current new
  current="$(get_forwards "$enc")"

  # Replace if the URL already exists, else append
  if [ -n "$current" ] && printf '%s\n' "$current" | awk -F'\t' -v u="$url" '$1==u{found=1} END{exit !found}'; then
    info "updating existing target for $path"
    new="$(printf '%s\n' "$current" | awk -F'\t' -v u="$url" -v k="$key" 'BEGIN{OFS="\t"} $1==u{print u,k;next}{print}')"
  else
    info "adding target to $path"
    if [ -n "$current" ]; then
      new="$(printf '%s\n%s\t%s' "$current" "$url" "$key")"
    else
      new="$(printf '%s\t%s' "$url" "$key")"
    fi
  fi

  printf '%s\n' "$new" | set_forwards "$enc"
  info "done. current $path targets:"
  get_forwards "$enc" | while IFS=$'\t' read -r u k; do
    [ -z "$u" ] && continue
    printf '  %s  key=%s\n' "$u" "${k:0:8}***"
  done
}

cmd_remove_forward() {
  local path="$1" url="$2"
  [ -n "$path" ] && [ -n "$url" ] || die "usage: $0 remove-forward <path> <url>"
  require_api

  local enc
  case "$path" in
    land) enc="$LAND_ENC" ;;
    vert) enc="$VERT_ENC" ;;
    *)   die "unknown path '$path' (use 'land' or 'vert')" ;;
  esac

  local current new
  current="$(get_forwards "$enc")"
  [ -n "$current" ] || { info "no targets on $path"; return 0; }
  new="$(printf '%s\n' "$current" | awk -F'\t' -v u="$url" '$1!=u')"
  printf '%s\n' "$new" | set_forwards "$enc"
  info "removed $url from $path"
}

case "${1:-}" in
  start)          cmd_start ;;
  stop)           cmd_stop ;;
  restart)        cmd_stop; sleep 1; cmd_start ;;
  status)         cmd_status ;;
  list)           cmd_list ;;
  add-forward|add) cmd_add_forward "${2:-}" "${3:-}" "${4:-}" ;;
  remove-forward|rm) cmd_remove_forward "${2:-}" "${3:-}" ;;
  *)
    cat <<EOF
${BOLD}relay.sh -- local multistream relay${NC}

  start                          start MediaMTX in the background
  stop                           stop MediaMTX
  restart                        stop then start
  status                         show server, active paths, forward targets
  list                           same as status

  add-forward <path> <url> [key]
                                  add a target, or replace the key if the URL
                                  already exists. Does NOT interrupt the stream.
  remove-forward <path> <url>    remove a target

paths: land (1920x1080), vert (1080x1920)

example:
  ./relay.sh add-forward vert "rtmps://live.tiktokcdn.com/live" "YOUR_KEY"
EOF
    exit 1
    ;;
esac
