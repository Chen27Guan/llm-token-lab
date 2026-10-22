#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${TOKENLAB_RELAY_HOST:?Set relay host}"
: "${TOKENLAB_RELAY_USER:?Set relay SSH user}"
: "${TOKENLAB_RELAY_KEY:?Set path to authorized SSH private key}"
PORT="${TOKENLAB_PORT:-38473}"
[[ "$PORT" =~ ^[0-9]+$ ]] && ((PORT>1024 && PORT<65536)) || { echo 'Invalid port'; exit 1; }
[ -f "$TOKENLAB_RELAY_KEY" ] || { echo 'SSH key not found'; exit 1; }
if screen -ls | grep -q '[.]tokenlab-relay[[:space:]]'; then echo 'tokenlab-relay already running'; exit 0; fi
mkdir -p var
export TOKENLAB_PORT="$PORT" TOKENLAB_RELAY_HOST TOKENLAB_RELAY_USER TOKENLAB_RELAY_KEY
export TOKENLAB_RELAY_SSH_PORT="${TOKENLAB_RELAY_SSH_PORT:-22}" TOKENLAB_RELAY_BIND="${TOKENLAB_RELAY_BIND:-127.0.0.1}"
screen -dmS tokenlab-relay bash scripts/relay.sh
echo "Started tokenlab-relay; inspect var/relay.log"
