#!/usr/bin/env bash
# List the relay's configured path patterns and their forward counts.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
curl -s "http://127.0.0.1:9997/v3/config/paths/list" -o "$DIR/test-out/cfg.json"
python3 "$DIR/../tools/dump-cfg-paths.py" < "$DIR/test-out/cfg.json"
