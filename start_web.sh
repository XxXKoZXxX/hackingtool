#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
pip install flask --quiet --break-system-packages --ignore-installed blinker 2>/dev/null || true
PORT="${PORT:-5000}"
echo ""
echo "  HackingTool Web UI"
echo "  Open: http://localhost:${PORT}"
echo ""
python3 webapp/app.py
