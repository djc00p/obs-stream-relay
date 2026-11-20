#!/usr/bin/env bash
# Run the twitch-token URL parsing self-test.
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 ./test-twitch-token.py
