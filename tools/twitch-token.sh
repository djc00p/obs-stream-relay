#!/usr/bin/env bash
# Get a Twitch user access token for stream metadata (title + category).
#
#   ./twitch-token.sh --client-id YOUR_CLIENT_ID
#
# Prints the authorize URL, opens it in your browser, and has you paste the
# redirect URL back. It extracts the token and validates it against Twitch.
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 ./twitch-token.py "$@"
