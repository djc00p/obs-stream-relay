#!/usr/bin/env bash
# Dump the relay's live path state.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$DIR/test-out"
curl -s "http://127.0.0.1:9997/v3/paths/list" -o "$DIR/test-out/paths-now.json"
python3 "$DIR/../tools/dump-paths.py" < "$DIR/test-out/paths-now.json"
