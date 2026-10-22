#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${TOKENLAB_RELAY_HOST:?Set relay host}"
: "${TOKENLAB_RELAY_USER:?Set relay SSH user}"
: "${TOKENLAB_RELAY_KEY:?Set authorized SSH key path}"
while true; do
 ssh -NT -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ConnectTimeout=10 -i "$TOKENLAB_RELAY_KEY" -p "${TOKENLAB_RELAY_SSH_PORT:-22}" -R "${TOKENLAB_RELAY_BIND:-127.0.0.1}:${TOKENLAB_PORT:-38473}:127.0.0.1:${TOKENLAB_PORT:-38473}" "$TOKENLAB_RELAY_USER@$TOKENLAB_RELAY_HOST" >> var/relay.log 2>&1 || true
 sleep 5
done
