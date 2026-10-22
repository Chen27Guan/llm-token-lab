#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo $$ > var/server.pid
exec "${TOKENLAB_PYTHON:-python}" -m uvicorn backend.app:app --host 127.0.0.1 --port "${TOKENLAB_PORT:-38473}" >> var/server.log 2>&1
