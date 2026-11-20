#!/usr/bin/env bash
# Set stream metadata (title, game/category) across platforms.
#
#   ./stream-meta.sh --title "..." --game "..."             # dry run
#   ./stream-meta.sh --title "..." --game "..." --apply     # push live
#   ./stream-meta.sh --check                                # read current values
#   ./stream-meta.sh --apply --only twitch,kick
#
# Credentials go in ~/Streaming-Relay/stream-meta.env (mode 600).
# RTMP itself carries no metadata -- this talks to each platform's API.
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 ./stream-meta.py "$@"
