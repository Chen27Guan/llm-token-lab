#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f var/server.pid ]; then
 pid=$(<var/server.pid)
 if [[ "$pid" =~ ^[0-9]+$ ]] && [ -r "/proc/$pid/cmdline" ] && [ "$(readlink -f /proc/$pid/cwd)" = "$PWD" ] && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q 'uvicorn backend.app:app'; then
  kill "$pid"
  for i in {1..50}; do kill -0 "$pid" 2>/dev/null || { echo "Stopped $pid"; exit 0; }; sleep 0.2; done
  echo 'Still shutting down; inspect before restarting'; exit 1
 fi
fi
