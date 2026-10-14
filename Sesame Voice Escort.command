#!/bin/bash
# Double-click launcher: starts the sesame-voice-escort server and opens the UI.
cd "$(dirname "$0")" || exit 1
( sleep 1; open "http://127.0.0.1:${PORT:-8377}" ) &
exec python3 server.py
