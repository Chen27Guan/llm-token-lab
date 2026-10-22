#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p var
PYTHON="${TOKENLAB_PYTHON:-python}"
PORT="${TOKENLAB_PORT:-38473}"
[[ "$PORT" =~ ^[0-9]+$ ]] && ((PORT>1024 && PORT<65536)) || { echo 'Invalid port'; exit 1; }
if screen -ls | grep -q '[.]tokenlab-app[[:space:]]'; then echo 'tokenlab-app already running'; exit 0; fi
export TOKENLAB_PYTHON="$PYTHON" TOKENLAB_PORT="$PORT"
screen -dmS tokenlab-app bash scripts/serve.sh
printf 'screen: tokenlab-app; HTTP port %s; log var/server.log\n' "$PORT"
