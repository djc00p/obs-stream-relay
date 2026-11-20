#!/usr/bin/env bash
# Run the kick-token self-test.
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 ./test-kick-token.py
