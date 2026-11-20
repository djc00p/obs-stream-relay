#!/usr/bin/env bash
# End-to-end check of the Kick token exchange path.
# Uses a fake client so the exchange fails at Kick's end -- but it must
# REACH Kick (a 4xx), not fail with a TLS error.
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 ./verify-kick-token-path.py
