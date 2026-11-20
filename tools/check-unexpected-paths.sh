#!/usr/bin/env bash
# Run the unexpected-paths detector and print the result.
#
#   ./tools/check-unexpected-paths.sh
#
# Exits 0 if the relay is carrying only the expected land/vert publishers.
# Exits 1 if there is at least one extra live path.
#
# Note: this is a bash wrapper because the exec preflight requires a direct
# `python <file>.py` form for python and a shell wrapper for the rest.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/unexpected-paths.py"
