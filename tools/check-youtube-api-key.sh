#!/usr/bin/env bash
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 ./check-youtube-api-key.py
