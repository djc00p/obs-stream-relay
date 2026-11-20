#!/usr/bin/env bash
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 ./test-oauth-state.py
