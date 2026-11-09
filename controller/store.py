"""SQLite store: the controller's memory and its audit trail.

One file, WAL mode, no server. It holds
  * decisions      — append-only audit log of every detection, decision and action, with evidence
  * proposals      — the full lifecycle of every config change we asked for (approval or auto-apply)
  * config_versions— every version of every workflow config we observed, with actor and the config
  * arms / dids / incidents / pins — learnt state that must survive a restart
  * kv             — small control-plane values (bootstrap facts, business defaults)
  * snapshots      — pickled aggregates + chunk watermark (written atomically together)
  * metrics/alerts — the loop's own health

Every write that matters is committed before the side effect it describes is attempted
("intent first"), so a restart can reconcile against the simulator.
"""
from __future__ import annotations

import json
import pickle
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT, last_chunk INTEGER NOT NULL, sim_minute INTEGER NOT NULL,
  wall_ts REAL NOT NULL, blob BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, sim_minute INTEGER NOT NULL, ts TEXT NOT NULL,
  workflow_id TEXT, kind TEXT NOT NULL, subject TEXT, summary TEXT NOT NULL, detail TEXT,
  proposal_id TEXT);
CREATE INDEX IF NOT EXISTS decisions_wf ON decisions(workflow_id, sim_minute);
CREATE INDEX IF NOT EXISTS decisions_prop ON decisions(proposal_id);
CREATE TABLE IF NOT EXISTS proposals (
  proposal_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, path TEXT NOT NULL, purpose TEXT NOT NULL,
  status TEXT NOT NULL, base_version INTEGER NOT NULL, created_minute INTEGER NOT NULL,
  submitted_minute INTEGER, approval_id TEXT, decided_minute INTEGER, applied_version INTEGER,
  applied_minute INTEGER, reasons TEXT, body TEXT NOT NULL, supersedes TEXT, updated_minute INTEGER);
CREATE INDEX IF NOT EXISTS proposals_wf ON proposals(workflow_id, status);
CREATE TABLE IF NOT EXISTS config_versions (
  workflow_id TEXT NOT NULL, version INTEGER NOT NULL, actor TEXT, changed_dims TEXT,
  proposal_id TEXT, approval_id TEXT, sim_minute INTEGER, ts TEXT, config TEXT,
  PRIMARY KEY (workflow_id, version));
CREATE TABLE IF NOT EXISTS arms (
  workflow_id TEXT NOT NULL, dim TEXT NOT NULL, segment TEXT NOT NULL, option TEXT NOT NULL,
  state TEXT NOT NULL, since_minute INTEGER NOT NULL, detail TEXT,
  PRIMARY KEY (workflow_id, dim, segment, option));
CREATE TABLE IF NOT EXISTS dids (
  workflow_id TEXT NOT NULL, did TEXT NOT NULL, state TEXT NOT NULL, since_minute INTEGER NOT NULL,
  detail TEXT, PRIMARY KEY (workflow_id, did));
CREATE TABLE IF NOT EXISTS incidents (
  id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL, kind TEXT NOT NULL,
  status TEXT NOT NULL, opened_minute INTEGER NOT NULL, updated_minute INTEGER NOT NULL,
  resolved_minute INTEGER, credits_spent REAL DEFAULT 0, detail TEXT);
CREATE TABLE IF NOT EXISTS pins (
  workflow_id TEXT NOT NULL, dim TEXT NOT NULL, since_minute INTEGER NOT NULL, version INTEGER,
  note TEXT, PRIMARY KEY (workflow_id, dim));
CREATE TABLE IF NOT EXISTS metrics (
  sim_minute INTEGER NOT NULL, wall_ts REAL NOT NULL, name TEXT NOT NULL, value REAL NOT NULL,
  labels TEXT);
CREATE INDEX IF NOT EXISTS metrics_name ON metrics(name, sim_minute);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, sim_minute INTEGER NOT NULL, severity TEXT NOT NULL,
  workflow_id TEXT, code TEXT NOT NULL, message TEXT NOT NULL, runbook TEXT,
  resolved_minute INTEGER);
"""


def _j(x) -> str | None:
    return None if x is None else json.dumps(x, sort_keys=True, default=str)


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), isolation_level=None, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        self.db.row_factory = sqlite3.Row
        self.clock = lambda: (0, "")  # (sim_minute, ts) — set by the controller

    # ------------------------------------------------------------------ helpers
    def tx(self):
        return _Tx(self.db)

    def q(self, sql: str, *args) -> list[sqlite3.Row]:
        return self.db.execute(sql, args).fetchall()

    def one(self, sql: str, *args):
        r = self.db.execute(sql, args).fetchone()
        return r

    # ------------------------------------------------------------------ kv
    def get(self, key: str, default=None):
        r = self.one("SELECT value FROM kv WHERE key=?", key)
        return default if r is None else json.loads(r[0])

    def put(self, key: str, value):
        self.db.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, json.dumps(value, sort_keys=True, default=str)))

    # ------------------------------------------------------------------ audit
    def decide(self, workflow_id: str | None, kind: str, summary: str, detail=None, subject: str | None = None,
               proposal_id: str | None = None) -> int:
        m, ts = self.clock()
        cur = self.db.execute("INSERT INTO decisions(sim_minute,ts,workflow_id,kind,subject,summary,detail,proposal_id)"
                              " VALUES(?,?,?,?,?,?,?,?)", (m, ts, workflow_id, kind, subject, summary, _j(detail),
                                                         proposal_id))
        return cur.lastrowid

    # ------------------------------------------------------------------ proposals
    def add_proposal(self, p: dict):
        self.db.execute(
            "INSERT INTO proposals(proposal_id,workflow_id,path,purpose,status,base_version,created_minute,body,"
            "supersedes,updated_minute) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (p["proposal_id"], p["workflow_id"], p["path"], p["purpose"], p["status"], p["base_version"],
             p["created_minute"], _j(p["body"]), p.get("supersedes"), p["created_minute"]))

    def update_proposal(self, pid: str, **fields):
        m, _ = self.clock()
        fields["updated_minute"] = m
        for k in ("reasons", "body"):
            if k in fields:
                fields[k] = _j(fields[k])
        sets = ",".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE proposals SET {sets} WHERE proposal_id=?", (*fields.values(), pid))

    def proposal(self, pid: str) -> dict | None:
        r = self.one("SELECT * FROM proposals WHERE proposal_id=?", pid)
        return _row(r)

    def proposals(self, workflow_id: str | None = None, statuses: tuple | None = None) -> list[dict]:
        sql, args = "SELECT * FROM proposals WHERE 1=1", []
        if workflow_id:
            sql += " AND workflow_id=?"
            args.append(workflow_id)
        if statuses:
            sql += f" AND status IN ({','.join('?' * len(statuses))})"
            args += list(statuses)
        return [_row(r) for r in self.q(sql + " ORDER BY created_minute, proposal_id", *args)]

    # ------------------------------------------------------------------ config versions
    def record_version(self, wid: str, version: int, actor: str, dims, proposal_id, approval_id, minute, ts,
                       config=None):
        self.db.execute(
            "INSERT INTO config_versions(workflow_id,version,actor,changed_dims,proposal_id,approval_id,sim_minute,"
            "ts,config) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(workflow_id,version) DO UPDATE SET "
            "config=COALESCE(excluded.config, config_versions.config)",
            (wid, version, actor, _j(dims), proposal_id, approval_id, minute, ts, _j(config)))

    # ------------------------------------------------------------------ learnt state
    def set_arm(self, wid, dim, segment, option, state, detail=None):
        m, _ = self.clock()
        self.db.execute("INSERT INTO arms VALUES(?,?,?,?,?,?,?) ON CONFLICT(workflow_id,dim,segment,option) DO UPDATE"
                        " SET state=excluded.state, since_minute=excluded.since_minute, detail=excluded.detail",
                        (wid, dim, segment, option, state, m, _j(detail)))

    def arms(self, wid: str) -> dict:
        return {(r["dim"], r["segment"], r["option"]): _row(r) for r in self.q("SELECT * FROM arms WHERE workflow_id=?", wid)}

    def set_did(self, wid, did, state, detail=None):
        m, _ = self.clock()
        self.db.execute("INSERT INTO dids VALUES(?,?,?,?,?) ON CONFLICT(workflow_id,did) DO UPDATE SET "
                        "state=excluded.state, since_minute=excluded.since_minute, detail=excluded.detail",
                        (wid, did, state, m, _j(detail)))

    def dids(self, wid: str) -> dict:
        return {r["did"]: _row(r) for r in self.q("SELECT * FROM dids WHERE workflow_id=?", wid)}

    def pins(self, wid: str) -> dict:
        return {r["dim"]: _row(r) for r in self.q("SELECT * FROM pins WHERE workflow_id=?", wid)}

    def pin(self, wid, dim, version, note):
        m, _ = self.clock()
        self.db.execute("INSERT INTO pins VALUES(?,?,?,?,?) ON CONFLICT(workflow_id,dim) DO UPDATE SET "
                        "since_minute=excluded.since_minute, version=excluded.version, note=excluded.note",
                        (wid, dim, m, version, note))

    # ------------------------------------------------------------------ incidents
    def open_incident(self, wid, kind, detail) -> int:
        m, _ = self.clock()
        cur = self.db.execute("INSERT INTO incidents(workflow_id,kind,status,opened_minute,updated_minute,detail)"
                              " VALUES(?,?,?,?,?,?)", (wid, kind, "open", m, m, _j(detail)))
        return cur.lastrowid

    def update_incident(self, iid: int, **fields):
        m, _ = self.clock()
        fields["updated_minute"] = m
        if "detail" in fields:
            fields["detail"] = _j(fields["detail"])
        sets = ",".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE incidents SET {sets} WHERE id=?", (*fields.values(), iid))

    def incidents(self, wid: str | None = None, open_only: bool = False) -> list[dict]:
        sql, args = "SELECT * FROM incidents WHERE 1=1", []
        if wid:
            sql += " AND workflow_id=?"
            args.append(wid)
        if open_only:
            sql += " AND status NOT IN ('resolved','abandoned')"
        return [_row(r) for r in self.q(sql + " ORDER BY id", *args)]

    # ------------------------------------------------------------------ observability
    def metric(self, name: str, value: float, labels=None):
        m, _ = self.clock()
        self.db.execute("INSERT INTO metrics VALUES(?,?,?,?,?)", (m, time.time(), name, float(value), _j(labels)))

    def alert(self, severity: str, code: str, message: str, workflow_id=None, runbook=None):
        m, _ = self.clock()
        open_ = self.one("SELECT id FROM alerts WHERE code=? AND IFNULL(workflow_id,'')=IFNULL(?, '') AND "
                         "resolved_minute IS NULL", code, workflow_id)
        if open_:
            return open_[0]
        cur = self.db.execute("INSERT INTO alerts(sim_minute,severity,workflow_id,code,message,runbook) VALUES"
                              "(?,?,?,?,?,?)", (m, severity, workflow_id, code, message, runbook))
        return cur.lastrowid

    def resolve_alert(self, code: str, workflow_id=None):
        m, _ = self.clock()
        self.db.execute("UPDATE alerts SET resolved_minute=? WHERE code=? AND IFNULL(workflow_id,'')=IFNULL(?, '') "
                        "AND resolved_minute IS NULL", (m, code, workflow_id))

    # ------------------------------------------------------------------ snapshots
    def save_snapshot(self, last_chunk: int, sim_minute: int, state: dict):
        blob = pickle.dumps(state, protocol=5)
        with self.tx():
            self.db.execute("INSERT INTO snapshots(last_chunk,sim_minute,wall_ts,blob) VALUES(?,?,?,?)",
                            (last_chunk, sim_minute, time.time(), blob))
            self.db.execute("DELETE FROM snapshots WHERE id NOT IN (SELECT id FROM snapshots ORDER BY id DESC LIMIT 2)")

    def load_snapshot(self) -> tuple[int, int, dict] | None:
        r = self.one("SELECT last_chunk, sim_minute, blob FROM snapshots ORDER BY id DESC LIMIT 1")
        if r is None:
            return None
        return r[0], r[1], pickle.loads(r[2])


class _Tx:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.execute("BEGIN IMMEDIATE")
        return self.db

    def __exit__(self, et, ev, tb):
        self.db.execute("COMMIT" if et is None else "ROLLBACK")
        return False


def _row(r) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    for k in ("detail", "reasons", "body", "changed_dims", "config", "labels"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    return d
