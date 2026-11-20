#!/usr/bin/env bash
# Debug helper: feed a fake Kick redirect URL to kick-token.py and show output.
#   ./debug-kick-token.sh "https://localhost/?code=abc123&state=xyz"
cd "$(dirname "${BASH_SOURCE[0]}")"
if [ "$#" -lt 1 ] || [ -z "$1" ]; then
  echo "usage: debug-kick-token.sh \"<redirect-url>\"" >&2
  exit 2
fi
printf '%s\n' "$1" | python3 ./kick-token.py \
    --client-id fakeid --client-secret fakesecret --no-open
