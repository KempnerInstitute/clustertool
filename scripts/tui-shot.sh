#!/usr/bin/env bash
# Render the dashboard in a real terminal of a given size and print what it drew.
# Usage: scripts/tui-shot.sh COLS ROWS [seconds]
set -u
cols=${1:-100}; rows=${2:-30}; wait=${3:-2}
session="tuishot_$$"
root="$(cd "$(dirname "$0")/.." && pwd)"
tmux new-session -d -s "$session" -x "$cols" -y "$rows" \
  "cd $root && .venv/bin/clustertool me; sleep 60"
sleep "$wait"
tmux capture-pane -p -t "$session"
tmux kill-session -t "$session" 2>/dev/null
