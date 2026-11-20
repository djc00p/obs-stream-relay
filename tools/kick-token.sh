#!/usr/bin/env bash
# Get a Kick access token for stream metadata (title + category).
#
#   ./kick-token.sh --client-id X --client-secret Y
#
# Kick uses OAuth 2.1 Authorization Code + PKCE, so it needs a client secret
# (unlike Twitch's implicit flow). The helper generates the PKCE verifier and
# challenge for you, opens the browser, and exchanges the code for a token.
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 ./kick-token.py "$@"
