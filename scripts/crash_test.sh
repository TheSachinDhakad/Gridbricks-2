#!/usr/bin/env bash
# Crash-recovery demonstration: run the controller against a live simulator, SIGKILL it at random
# moments several times, restart it each time with the same state directory, let it finish, then
# verify invariants and grade.
#   scripts/crash_test.sh [scenario.yaml] [kills] [port]
set -euo pipefail
cd "$(dirname "$0")/.."
SCEN="${1:-scenarios/public_02_incidents.yaml}"
KILLS="${2:-4}"
PORT="${3:-8720}"
NAME="$(basename "$SCEN" .yaml)"
PY="${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}"
URL="http://127.0.0.1:$PORT"
STATE="state/crash"
LOG="reports/crash_recovery_$NAME.log"
mkdir -p reports runs "$STATE"
rm -f "$STATE/$NAME".db*
[ -d "runs/base_$NAME" ] || "$PY" -m sim baseline --scenario "$SCEN" --run-dir "runs/base_$NAME"
"$PY" -m sim serve --scenario "$SCEN" --run-dir "runs/crash_$NAME" --port "$PORT" --force > "runs/sim_crash_$NAME.log" 2>&1 &
SIM=$!
trap 'kill $SIM 2>/dev/null || true' EXIT
until curl -sf "$URL/health" >/dev/null; do sleep 0.5; done

: > "$LOG"
say() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
clock() { curl -s "$URL/sim/state" | "$PY" -c 'import json,sys; s=json.load(sys.stdin); print(s["ts"], "minute", s["sim_minute"])'; }

for i in $(seq 1 "$KILLS"); do
  STATE_DIR="$STATE" PYTHON="$PY" ./run.sh "$URL" >> "runs/crash_controller_$NAME.log" 2>&1 &
  CTL=$!
  sleep "$(( RANDOM % 4 + 2 )).$(( RANDOM % 10 ))"
  if kill -0 "$CTL" 2>/dev/null; then
    kill -9 "$CTL"; wait "$CTL" 2>/dev/null || true
    say "kill -9 #$i at sim $(clock); pending proposals in store: $(sqlite3 "$STATE/$NAME.db" "select count(*) from proposals where status in ('pending','approved','submitting')" 2>/dev/null || echo n/a)"
  else
    say "controller already finished before kill #$i"
  fi
done
say "final restart; running to completion"
STATE_DIR="$STATE" PYTHON="$PY" ./run.sh "$URL" >> "runs/crash_controller_$NAME.log" 2>&1
say "finished at sim $(clock)"
"$PY" scripts/verify_run.py --url "$URL" --db "$STATE/$NAME.db" | tee -a "$LOG"
"$PY" -m sim grade --run "runs/crash_$NAME" --baseline "runs/base_$NAME" --out "reports/crash_recovery_${NAME}_grade.md" > /dev/null
sed -n '5,12p' "reports/crash_recovery_${NAME}_grade.md" | tee -a "$LOG"
grep -E "applied —" "reports/crash_recovery_${NAME}_grade.md" | tee -a "$LOG"
say "restart decisions in audit log:"
"$PY" -m controller audit --db "$STATE/$NAME.db" --kind 'restart' --limit 20 | tee -a "$LOG"
"$PY" -m controller audit --db "$STATE/$NAME.db" --kind 'reconcile' --limit 20 | tee -a "$LOG"
