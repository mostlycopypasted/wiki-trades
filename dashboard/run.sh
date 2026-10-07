#!/bin/bash
# Start the Trading Desk dashboard: http://127.0.0.1:8787 (override with PORT=9000 ./dashboard/run.sh)
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python3
[ -x "$PY" ] || PY=python3
exec "$PY" dashboard/server.py --port "${PORT:-8787}" "$@"
