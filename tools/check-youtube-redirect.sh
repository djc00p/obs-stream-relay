#!/usr/bin/env bash
# Shows which redirect URI is registered on the YouTube OAuth client.
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 -c "
import sys, os, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath('.')))
from youtube_token_probe import probe_all
probe_all()
"
