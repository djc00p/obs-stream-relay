#!/usr/bin/env bash
# Run the unexpected-paths detector self-test.
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 ./test-unexpected-paths.py
