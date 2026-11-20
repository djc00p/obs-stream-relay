#!/usr/bin/env bash
# Debug helper: feed a fake redirect URL to twitch-token.py and show output.
#   ./debug-twitch-token.sh "https://localhost/#access_token=abc123"
cd "$(dirname "${BASH_SOURCE[0]}")"
if [ "$#" -lt 1 ] || [ -z "$1" ]; then
  echo "usage: debug-twitch-token.sh \"<redirect-url>\"" >&2
  exit 2
fi
printf '%s\n' "$1" | python3 ./twitch-token.py --client-id fake --no-open
