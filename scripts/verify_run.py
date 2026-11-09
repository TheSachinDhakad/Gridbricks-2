"""Check a finished run's invariants against the simulator API and the controller store.

    python scripts/verify_run.py --url http://127.0.0.1:8720 --db state/public_02_incidents.db

Exits non-zero if any of these fail:
  * the scenario finished
  * no proposal_id appears twice in any workflow's config history (no double apply)
  * every version the simulator attributes to us is recorded as applied in our store, and vice versa
  * every approval left unapplied is explained in our store (withdrawn / stale base / lapsed)
  * nothing in our store is stuck in 'planned' / 'submitting'
"""
import argparse
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from controller.store import Store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--db", required=True)
    a = ap.parse_args()
    c = httpx.Client(base_url=a.url, timeout=60)
    s = Store(a.db)
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + msg)
        ok &= bool(cond)

    st = c.get("/sim/state").json()
    check(st["finished"], f"scenario finished at minute {st['sim_minute']}")
    sim_applied = set()
    for w in c.get("/workflows").json():
        hist = c.get(f"/workflows/{w['workflow_id']}/config/history").json()
        pids = [v["proposal_id"] for v in hist if v["proposal_id"]]
        check(len(pids) == len(set(pids)), f"{w['workflow_id']}: {len(pids)} controller versions, no duplicates")
        sim_applied |= set(pids)
    ours = {p["proposal_id"] for p in s.proposals() if p["status"] == "applied"}
    check(ours == sim_applied, f"store and simulator agree on {len(ours)} applied proposals")
    stuck = s.proposals(statuses=("planned", "submitting"))
    check(not stuck, f"no proposals stuck mid-submission ({len(stuck)})")
    approved = c.get("/approvals", params={"status": "approved"}).json()
    withdrawn = {p["approval_id"] for p in s.proposals(statuses=("withdrawn", "stale", "lapsed"))}
    unexplained = [x["approval_id"] for x in approved if x["approval_id"] not in withdrawn]
    check(not unexplained, f"every approved-but-unapplied approval is explained in our store as withdrawn/stale/"
                           f"lapsed ({len(approved) - len(unexplained)} explained, {len(unexplained)} unexplained)")
    restarts = s.one("SELECT COUNT(*) FROM decisions WHERE kind='restart'")[0]
    print(f"INFO controller restarts recorded in audit log: {restarts}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
