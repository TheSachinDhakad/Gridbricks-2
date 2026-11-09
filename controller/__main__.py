"""CLI.

  python -m controller run    --url http://127.0.0.1:8700 [--state-dir state]
  python -m controller view   [--db state/<scenario>.db] [--workflow ID]
  python -m controller why    --workflow ID --at "D3 14:00" [--db ...]
  python -m controller health [--db ...]
  python -m controller audit  [--workflow ID] [--kind KIND] [--limit N] [--db ...]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .store import Store


def _latest_db(state_dir: str) -> Path:
    dbs = sorted(Path(state_dir).glob("*.db"), key=lambda p: p.stat().st_mtime)
    if not dbs:
        sys.exit(f"no controller database in {state_dir}/")
    return dbs[-1]


def cmd_run(a):
    from .controller import Controller
    from .simclient import Sim
    state_dir = Path(a.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    sim = Sim(a.url)
    sim.wait_ready()
    st = sim.state()
    db = state_dir / f"{st['scenario']}.db"
    logging.basicConfig(level=getattr(logging, a.log_level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(state_dir / f"{st['scenario']}.log")])
    logging.getLogger("httpx").setLevel(logging.WARNING)
    hist = sim.chunks("history", -1)
    fingerprint = {"scenario": st["scenario"], "chunk0": hist[0] if hist else None}
    if db.exists():
        s = Store(db)
        old = s.get("world")
        last = s.get("last_minute", -10**9)
        s.db.close()
        if old != fingerprint or last > st["sim_minute"]:
            dst = db.with_suffix(f".db.stale-{int(time.time())}")
            db.rename(dst)
            for ext in ("-wal", "-shm"):
                p = Path(str(db) + ext)
                if p.exists():
                    p.rename(Path(str(dst) + ext))
            logging.warning("existing state belongs to a different world; archived to %s", dst)
    store = Store(db)
    store.put("world", fingerprint)
    ctl = Controller(sim, store)
    t0 = time.time()
    ctl.bootstrap()
    logging.info("bootstrapped in %.1fs at sim minute %s", time.time() - t0, ctl.now)
    orig = ctl._set_clock

    def clock(st):  # remember how far we got, for the world-identity check on restart
        orig(st)
        store.put("last_minute", st["sim_minute"])
    ctl._set_clock = clock
    ctl.run()
    logging.info("finished in %.1fs wall: %s", time.time() - t0, ctl.stats)
    out = state_dir / f"{st['scenario']}_supervisor_view.md"
    from .views import supervisor_view, workflows
    out.write_text("\n\n".join(supervisor_view(store, w) for w in workflows(store)))
    logging.info("supervisor view written to %s", out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="controller")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--url", required=True)
    r.add_argument("--state-dir", default="state")
    r.add_argument("--log-level", default="info")
    for name in ("view", "why", "health", "audit"):
        p = sub.add_parser(name)
        p.add_argument("--db")
        p.add_argument("--state-dir", default="state")
        p.add_argument("--workflow")
        if name == "why":
            p.add_argument("--at", required=True, help='e.g. "D3 14:00"')
        if name == "audit":
            p.add_argument("--kind")
            p.add_argument("--limit", type=int, default=50)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return cmd_run(a)
    from . import views
    store = Store(a.db or _latest_db(a.state_dir))
    if a.cmd == "view":
        wfs = [a.workflow] if a.workflow else views.workflows(store)
        print("\n\n".join(views.supervisor_view(store, w) for w in wfs))
    elif a.cmd == "why":
        print(views.why(store, a.workflow, views.parse_when(a.at)))
    elif a.cmd == "health":
        print(views.health(store))
    elif a.cmd == "audit":
        sql, args = "SELECT * FROM decisions WHERE 1=1", []
        if a.workflow:
            sql += " AND workflow_id=?"
            args.append(a.workflow)
        if a.kind:
            sql += " AND kind LIKE ?"
            args.append(a.kind)
        for r in store.q(sql + " ORDER BY id DESC LIMIT ?", *args, a.limit)[::-1]:
            print(f"{views.fmt(r['sim_minute'])} {r['workflow_id'] or '-':<14} {r['kind']:<22} {r['summary']}")


if __name__ == "__main__":
    main()
