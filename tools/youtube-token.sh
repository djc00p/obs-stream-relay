#!/usr/bin/env bash
# YouTube OAuth token helper. Writes YT_TOKEN into stream-meta.env.
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 ./youtube-token.py "$@"
