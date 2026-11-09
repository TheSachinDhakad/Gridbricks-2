#!/usr/bin/env bash
# Starts the controller against a running simulator and runs until the scenario finishes.
#   ./run.sh <SIM_URL>
# No Docker: plain Python 3.10+ with requirements.txt installed (numpy, httpx; sqlite3 is stdlib).
# State lives in ./state/<scenario>.db (override with STATE_DIR). Restarting with the same simulator
# resumes from that state; a different/new simulator world is detected and starts fresh.
set -euo pipefail
SIM_URL="${1:?usage: ./run.sh <SIM_URL>}"
cd "$(dirname "$0")"
PY="${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}"
exec "$PY" -m controller run --url "$SIM_URL" --state-dir "${STATE_DIR:-state}" --log-level "${LOG_LEVEL:-info}"
