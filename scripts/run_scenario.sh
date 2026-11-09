#!/usr/bin/env bash
# Run one scenario end to end: baseline, simulator, controller, grade.
#   scripts/run_scenario.sh scenarios/public_01_dev.yaml [port]
set -euo pipefail
cd "$(dirname "$0")/.."
SCEN="${1:?scenario yaml}"
PORT="${2:-8700}"
NAME="$(basename "$SCEN" .yaml)"
PY="${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}"
mkdir -p reports runs state
[ -d "runs/base_$NAME" ] || "$PY" -m sim baseline --scenario "$SCEN" --run-dir "runs/base_$NAME"
rm -f "state/$NAME.db" "state/$NAME.db-wal" "state/$NAME.db-shm"
"$PY" -m sim serve --scenario "$SCEN" --run-dir "runs/mine_$NAME" --port "$PORT" --force > "runs/sim_$NAME.log" 2>&1 &
SIM_PID=$!
trap 'kill $SIM_PID 2>/dev/null || true' EXIT
START=$(date +%s)
PYTHON="$PY" ./run.sh "http://127.0.0.1:$PORT"
echo "controller wall time: $(( $(date +%s) - START ))s"
"$PY" -m sim grade --run "runs/mine_$NAME" --baseline "runs/base_$NAME" --out "reports/$NAME.md" > /dev/null
echo "report: reports/$NAME.md"
