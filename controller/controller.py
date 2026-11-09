"""The controller loop: ingest → detect → decide → propose/apply → learn, for every workflow.

Read this file top to bottom; it is the map of the system. Statistical logic lives in
experiments.py / callerid.py / schedule.py / incidents.py; governance rules in governance.py.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import logging
import os
import resource
import time
import uuid

import numpy as np

from . import callerid
from . import settings as S
from .aggregates import Ingestor, WFAgg
from .configtools import AGENT_DIMS, changed_dims, describe_diff, dist, step_toward, take_dims, tv
from .experiments import DIMS, ExperimentEngine
from .features import NCELL, Cohort, Vocab, cohort_index
from .governance import Policy, inflight, may_submit
from .incidents import check_spike, flag_baseline, proven_prompts, window_counts
from .schedule import build_partition, hour_weights_for, learn_schedule, partition_size
from .simclient import ApiError, Sim
from .stats import poisson_sf, ratio_test
from .store import Store

log = logging.getLogger("controller")


def fault(point: str):
    """Crash-test hook: CONTROLLER_FAULT=<point> makes the process die right after that side effect,
    before it is recorded — the most dangerous moment for idempotency. Fires once per state dir."""
    want = os.environ.get("CONTROLLER_FAULT")
    marker = os.environ.get("CONTROLLER_FAULT_MARKER")
    if want == point and marker and not os.path.exists(marker):
        open(marker, "w").write(point)
        log.error("fault injection: dying right after %s", point)
        os._exit(137)


def fmt_minute(m: int) -> str:
    d, mod = divmod(m, 1440)
    return f"D{d} {mod // 60:02d}:{mod % 60:02d}"


class Controller:
    def __init__(self, sim: Sim, store: Store):
        self.sim, self.store = sim, store
        self.meta: dict[str, dict] = {}
        self.pol: dict[str, Policy] = {}
        self.aggs: dict[str, WFAgg] = {}
        self.vocab = Vocab()
        self.ing: Ingestor | None = None
        self.last_chunk = -1
        self.snap_minute = None
        self.now, self.ts = 0, ""
        self.cfg: dict[str, dict] = {}
        self.engines: dict[str, ExperimentEngine] = {}
        self.stats = {"events": 0, "ingest_s": 0.0, "decide_s": 0.0, "advance_s": 0.0}
        store.clock = lambda: (self.now, self.ts)

    # ================================================================== bootstrap & recovery
    def _set_clock(self, st: dict):
        self.now, self.ts = st["sim_minute"], st["ts"]

    def bootstrap(self):
        st = self.sim.state()
        self._set_clock(st)
        day0 = (dt.datetime.fromisoformat(st["ts"]) - dt.timedelta(minutes=st["sim_minute"])).date()
        for w in self.sim.workflows():
            self.meta[w["workflow_id"]] = w
            self.pol[w["workflow_id"]] = Policy.from_meta(w)
        if self.store.get("epoch") is None:
            self.store.put("epoch", uuid.uuid4().hex[:6])
        snap = self.store.load_snapshot()
        if snap:
            self.last_chunk, self.snap_minute, state = snap
            self.aggs, self.vocab = state["aggs"], Vocab(state["vocab"])
            self.store.decide(None, "restart", f"resumed from snapshot at {fmt_minute(self.snap_minute)} "
                              f"(chunk {self.last_chunk}); replaying newer chunks", {"last_chunk": self.last_chunk})
            log.info("restored snapshot: chunk %s, %s", self.last_chunk, fmt_minute(self.snap_minute))
        for wid, m in self.meta.items():
            self.aggs.setdefault(wid, WFAgg(m["options"]))
        self.ing = Ingestor(self.aggs, self.vocab, day0)
        self.ingest_new()
        if not self.store.get("bootstrapped"):
            self._learn_from_history()
        for wid in self.meta:
            self._engine(wid)
        self._reconcile()

    def _engine(self, wid) -> ExperimentEngine:
        e = self.engines.get(wid)
        if e is None:
            g = self.meta[wid]["objective"].get("guardrail") or {}
            max_drop = float(next(iter(g.values()), 0.02))
            e = self.engines[wid] = ExperimentEngine(self.store, wid, self.aggs[wid], self.vocab,
                                                     self.store.get(f"control:{wid}") or {}, max_drop)
        return e

    def _learn_from_history(self):
        """C3: everything we can learn before D0 — business default, baselines, DIDs, call-time."""
        for wid, m in self.meta.items():
            agg = self.aggs[wid]
            c = self.sim.config(wid)
            cfg = c["config"]
            self.store.record_version(wid, c["version"], c["actor"], [], None, None, self.now, self.ts, cfg)
            control = {d: max(dist(cfg, "default", d).items(), key=lambda kv: kv[1])[0] for d in DIMS}
            self.store.put(f"control:{wid}", control)
            hist = [d for d in agg.days() if d < 0]
            dials = conn = eng = 0
            for d in hist:
                k = agg.daily_kpis(d)
                dials, conn, eng = dials + k["dials"], conn + k["connected"], eng + k["engaged"]
            up = sum(int(agg.uploaded[d].sum()) for d in agg.uploaded if d < 0)
            concl = sum(int(agg.concluded[d].sum()) for d in agg.concluded if d < 0)
            base = {"pickup": conn / max(dials, 1), "engagement": eng / max(conn, 1),
                    "conclusion": concl / max(up, 1), "dials_per_day": dials / max(len(hist), 1), "days": len(hist)}
            self.store.put(f"baseline:{wid}", base)
            b0, n0 = flag_baseline(agg)
            self.store.put(f"b0:{wid}", b0)
            D = agg.sum_days(agg.did, hist)
            for i, did in enumerate(agg.D):
                n = 0 if D is None else int(D[:, i, 0].sum())
                st = "healthy" if n >= 500 else "unknown"
                self.store.set_did(wid, did, st, {"reason": "history", "history_dials": n,
                                                  "history_pickup": round(int(D[:, i, 1].sum()) / n, 4) if n else None})
            sched = learn_schedule(agg, self.vocab, hist, tuple(m["dialling_window"]))
            self.store.put(f"sched:{wid}", sched)
            self.store.decide(wid, "bootstrap", f"learnt from {len(hist)} history days: pickup {base['pickup']:.1%}, "
                              f"engagement {base['engagement']:.1%}, flag rate {b0:.2%}; control "
                              f"{control}; call-time feature {sched and sched.get('feature')}",
                              {"baseline": base, "control": control, "flag_baseline": b0, "flag_n": n0,
                               "schedule": sched, "dids": {d: r["state"] for d, r in self.store.dids(wid).items()}})
        self.store.put("bootstrapped", True)

    def _reconcile(self):
        """After a restart: find out what happened to anything we were in the middle of."""
        for p in self.store.proposals(statuses=("planned", "submitting")):
            wid, pid = p["workflow_id"], p["proposal_id"]
            if p["path"] == "approval":
                hit = [a for a in self.sim.approvals(workflow_id=wid) if a["proposal_id"] == pid]
                if hit:
                    a = hit[0]
                    self.store.update_proposal(pid, status="pending", approval_id=a["approval_id"])
                    self.store.decide(wid, "reconcile", f"proposal {pid} had reached the approver as "
                                      f"{a['approval_id']} before the crash", proposal_id=pid)
                else:
                    self.store.update_proposal(pid, status="not_sent")
                    self.store.decide(wid, "reconcile", f"proposal {pid} never reached the simulator; "
                                      "will re-plan from fresh data", proposal_id=pid)
            else:
                hist = self.sim.config_history(wid)
                hit = [v for v in hist if v["proposal_id"] == pid]
                if hit:
                    self.store.update_proposal(pid, status="applied", applied_version=hit[0]["version"])
                    self.store.decide(wid, "reconcile", f"auto-apply {pid} had landed as v{hit[0]['version']}",
                                      proposal_id=pid)
                else:
                    self.store.update_proposal(pid, status="not_sent")
        self._post_apply_incident_sync()

    # ================================================================== ingestion
    def ingest_new(self) -> int:
        chunks = self.sim.chunks("history", self.last_chunk) + self.sim.chunks("events", self.last_chunk)
        chunks.sort(key=lambda c: c["chunk"])
        n_total = 0
        for ch in chunks:
            t0 = time.perf_counter()
            data = self.sim.chunk(ch["chunk"])
            n, control = self.ing.ingest(data)
            self.last_chunk = ch["chunk"]
            self._handle_control(control)
            dt_ = time.perf_counter() - t0
            self.stats["events"] += n
            self.stats["ingest_s"] += dt_
            n_total += n
            if n > 1000:
                self.store.metric("ingest_events_per_s", n / max(dt_, 1e-6), {"chunk": ch["chunk"]})
        return n_total

    def _handle_control(self, events: list[dict]):
        seen = self.store.get("ctl_event_id", 0)
        top = seen
        for ev in events:
            if ev["event_id"] <= seen:
                continue  # replayed after a restart: already handled
            top = max(top, ev["event_id"])
            if ev["type"] != "config_changed":
                continue
            wid = ev["workflow_id"]
            self.store.record_version(wid, ev["version"], ev["actor"], ev.get("changed_dims"), ev.get("proposal_id"),
                                      ev.get("approval_id"), self._ev_minute(ev), ev["ts"])
            if ev["actor"] == "supervisor":
                dims = ev.get("changed_dims") or []
                for d in dims:
                    self.store.pin(wid, d, ev["version"], f"supervisor edit v{ev['version']} at {ev['ts']}")
                stale = [p["proposal_id"] for p in inflight(self.store, wid)]
                self.store.decide(wid, "supervisor_edit",
                                  f"supervisor changed {', '.join(dims)} (v{ev['version']}); we keep their values for "
                                  f"these dims from now on" + (f"; in-flight {stale} will need re-proposing" if stale else ""),
                                  {"version": ev["version"], "changed_dims": dims, "ts": ev["ts"],
                                   "inflight_affected": stale})
                self.store.alert("ticket", "supervisor_edit", f"{wid}: supervisor edited {dims} at {ev['ts']}",
                                 wid, "No action needed; check the supervisor view if an experiment was paused.")
        if top > seen:
            self.store.put("ctl_event_id", top)

    def _ev_minute(self, ev) -> int:
        t = dt.datetime.fromisoformat(ev["ts"])
        d0 = dt.datetime.combine(self.ing.day0, dt.time(), tzinfo=t.tzinfo)
        return int((t - d0).total_seconds() // 60)

    def snapshot(self, force=False):
        if not force and self.snap_minute is not None and self.now - self.snap_minute < S.SNAPSHOT_EVERY_MIN:
            return
        t0 = time.perf_counter()
        self.store.save_snapshot(self.last_chunk, self.now, {"aggs": self.aggs, "vocab": self.vocab.to_state()})
        self.snap_minute = self.now
        self.store.metric("snapshot_s", time.perf_counter() - t0)

    # ================================================================== main loop
    def run(self, max_wall_s: float | None = None):
        t_start = time.time()
        while True:
            st = self.sim.state()
            self._set_clock(st)
            t0 = time.perf_counter()
            self.decide(st)
            self.stats["decide_s"] += time.perf_counter() - t0
            self.snapshot()
            if st["finished"]:
                break
            if max_wall_s and time.time() - t_start > max_wall_s:
                log.warning("wall-clock budget exhausted; stopping")
                break
            t0 = time.perf_counter()
            st = self.sim.advance_to(self._next_minute(st))
            self.stats["advance_s"] += time.perf_counter() - t0
            self._set_clock(st)
            t0 = time.perf_counter()
            n = self.ingest_new()
            self.store.metric("ingest_lag_chunks", len(self.sim.chunks("events", self.last_chunk)))
            if self.now % 1440 == 0:
                self._daily_metrics()
            log.debug("%s ingested %d events", fmt_minute(self.now), n)
        self.finish()

    def _next_minute(self, st) -> int:
        now, end = st["sim_minute"], st["end_minute"]
        lo = min(min(m["dialling_window"][0] for m in self.meta.values()),
                 min(p.approver_hours[0] for p in self.pol.values())) - 2
        hi = max(max(m["dialling_window"][1] for m in self.meta.values()),
                 max(p.approver_hours[1] + p.apply_window_hours for p in self.pol.values()))
        day, mod = divmod(now, 1440)
        if lo * 60 <= mod < hi * 60:
            nxt = now + S.ACTIVE_STEP_MIN
        elif mod < lo * 60:
            nxt = day * 1440 + int(lo * 60)
        else:
            nxt = (day + 1) * 1440 + int(lo * 60)
        return min(nxt, end)

    def finish(self):
        self.ingest_new()
        self.snapshot(force=True)
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_mb = peak / (1024 * 1024) if peak > 1e7 else peak / 1024  # macOS bytes, Linux KiB
        self.store.metric("peak_rss_mb", peak_mb)
        self.store.put("run_stats", {**self.stats, "peak_rss_mb": round(peak_mb, 1), "sim_calls": self.sim.calls})
        self.store.decide(None, "finished", f"scenario finished; {self.stats['events']} events ingested",
                          {k: round(v, 2) if isinstance(v, float) else v for k, v in self.stats.items()})

    def _daily_metrics(self):
        st = self.sim.state()
        self.store.metric("credits_remaining", st["credits_remaining"])
        day = self.now // 1440 - 1
        for wid, agg in self.aggs.items():
            k = agg.daily_kpis(day)
            if k["dials"]:
                self.store.metric("pickup_rate", k["connected"] / k["dials"], {"wf": wid, "day": day})
                self.store.metric("engagement_rate", k["engaged"] / max(k["connected"], 1), {"wf": wid, "day": day})
        n = self.store.one("SELECT COUNT(*) FROM decisions WHERE sim_minute > ?", self.now - 1440)[0]
        self.store.metric("decisions_per_day", n)

    # ================================================================== the decision cycle
    def decide(self, st: dict):
        if self.store.proposals(statuses=("planned", "submitting")):
            self._reconcile()  # an earlier POST had an ambiguous outcome
        self._process_inflight()
        day, mod = divmod(self.now, 1440)
        hour = mod // 60
        on_the_hour = mod % 60 == 0
        for wid, m in self.meta.items():
            pol = self.pol[wid]
            cur = self._config(wid)
            lo, hi = m["dialling_window"]
            dialling = lo - 1 <= hour < hi + 1
            protective = False
            for inc in self.store.incidents(wid, open_only=True):
                if inc["kind"] == "did_degraded" and inc["detail"]["did"] not in dist(cur["config"], "default", "caller_id"):
                    self.store.update_incident(inc["id"], status="resolved", resolved_minute=self.now)
                    self.store.decide(wid, "incident_resolved", f"caller ID {inc['detail']['did']} no longer dialled "
                                      f"(v{cur['version']})", inc["detail"], subject=f"incident:{inc['id']}")
                    self.store.resolve_alert(f"did_bad:{inc['detail']['did']}", wid)
            if dialling:
                for t in callerid.evaluate(self.store, wid, self.aggs[wid], day, hour, self._eng_max_drop(wid)):
                    protective |= t["protective"]
                    if t["state"] == "bad":
                        self.store.open_incident(wid, "did_degraded", t)
                        self.store.alert("ticket", f"did_bad:{t['did']}", f"{wid}: {t['summary']}", wid,
                                         "Controller rotates the number out automatically where policy allows; "
                                         "otherwise a protective approval is queued. Check carrier spam status.")
                self._hallucination_step(wid, cur, st)
            if on_the_hour and dialling or self._routine_due(wid):
                guard = self._guardrail(wid, day) if on_the_hour else (self.store.get(f"guard:{wid}") or {})
                for t in self._engine(wid).evaluate(day, set(self.store.pins(wid)), self._split_features(wid),
                                                    lambda dim, f, w=wid: self._can_split(w, dim, f),
                                                    pressure=guard.get("pressure") and guard.get("kpi") == "engagement_rate"):
                    protective |= t["protective"]
                    if t["state"] == "decayed":
                        self.store.alert("ticket", f"decay:{t['dim']}:{t['option']}", f"{wid}: {t['summary']}", wid,
                                         "Rollback is automatic (auto-apply or protective approval).")
            if protective:
                self.store.put(f"protective:{wid}", self.now)
            if dialling or pol.in_approver_hours(self.now) or self._routine_due(wid):
                self._plan(wid, cur, bool(self.store.get(f"protective:{wid}")))
        self._alerts_sweep(st)

    def _guardrail(self, wid: str, day: int) -> dict:
        """Workflow-level guardrail KPI over the last ~2 days vs. history (stakeholders/05, README §5.3)."""
        g = self.meta[wid]["objective"].get("guardrail") or {}
        if not g:
            return {}
        key, max_drop = next(iter(g.items()))
        kpi = "pickup_rate" if key.startswith("pickup") else "engagement_rate"
        base = self.store.get(f"baseline:{wid}") or {}
        agg = self.aggs[wid]
        k = [agg.daily_kpis(d) for d in (day - 1, day)]
        dials, conn, eng = (sum(x[f] for x in k) for f in ("dials", "connected", "engaged"))
        if kpi == "pickup_rate":
            num, den, b = conn, dials, base.get("pickup")
            bn = base.get("dials_per_day", 0) * base.get("days", 0)
        else:
            num, den, b = eng, conn, base.get("engagement")
            bn = base.get("dials_per_day", 0) * base.get("days", 0) * base.get("pickup", 0)
        if not den or b is None or den < 300:
            return {}
        from .stats import diff_z
        d, z = diff_z(num, den, b * bn, bn)
        st = {"kpi": kpi, "baseline": round(b, 4), "recent": round(num / den, 4), "drop": round(-d, 4), "z": round(z, 2),
              "max_drop": max_drop, "pressure": bool(-d > S.GUARD_PRESSURE_FRACTION * max_drop and z <= -2)}
        prev = self.store.get(f"guard:{wid}") or {}
        if st["pressure"] != prev.get("pressure"):
            self.store.decide(wid, "guardrail_pressure" if st["pressure"] else "guardrail_ok",
                              f"{kpi} over the last 2 days {num/den:.1%} vs {b:.1%} before D0 (drop {-d:+.3f}, allowed "
                              f"{max_drop}); " + ("stopping challengers that lower it" if st["pressure"] else "back to normal"),
                              st)
        if -d > max_drop and z <= -2:
            self.store.alert("ticket", "guardrail_breach", f"{wid}: {kpi} {num/den:.1%} vs {b:.1%} baseline (drop "
                             f"{-d:.3f} > {max_drop})", wid, "Check recent changes in `controller why`; composition "
                             "shifts from call-time changes are the usual cause.")
        self.store.put(f"guard:{wid}", st)
        return st

    def _routine_due(self, wid) -> bool:
        return self.pol[wid].routine_window(self.now)

    def _eng_max_drop(self, wid) -> float:
        g = self.meta[wid]["objective"].get("guardrail") or {}
        return float(g.get("engagement_rate_max_drop", 0.05))

    def _config(self, wid, refresh=False) -> dict:
        c = self.sim.config(wid)
        if self.cfg.get(wid, {}).get("version") != c["version"]:
            self.store.record_version(wid, c["version"], c["actor"], None, None, None, self.now, self.ts, c["config"])
        self.cfg[wid] = c
        return c

    # ================================================================== planning
    def _split_features(self, wid) -> dict:
        return dict(self.store.get(f"split:{wid}") or {})

    def _splits(self, wid) -> list[tuple[str, list[list[str]]]]:
        sf = self._split_features(wid)
        arms = self.store.arms(wid)
        by_feat: dict[str, set] = {}
        for (dim, seg, opt), row in arms.items():
            if seg == "all" or row["state"] not in ("winner", "excluded"):
                continue
            f, v = seg.split("=", 1)
            if sf.get(dim) == f:
                by_feat.setdefault(f, set()).add(v)
        return [(f, [[v] for v in sorted(vs)]) for f, vs in sorted(by_feat.items())]

    def _can_split(self, wid, dim, feat) -> bool:
        sf = self._split_features(wid)
        if sf.get(dim) and sf[dim] != feat:
            return False
        if self.store.pins(wid).keys() & {"cohorts", "welcome_message", "voice", "caller_id", "schedule"}:
            return False
        sched = self.store.get(f"sched:{wid}") or {}
        splits = self._splits(wid)
        feats = {f: len(g) for f, g in splits}
        feats[feat] = feats.get(feat, 0) + 1
        n = max(len(sched.get("values") or []), 1) if sched.get("feature") else 1
        for f, k in feats.items():
            if f != sched.get("feature"):
                n *= k + 1
        ok = n <= S.MAX_COHORTS
        if ok and not sf.get(dim):
            sf[dim] = feat
            self.store.put(f"split:{wid}", sf)
        return ok

    def compose(self, wid: str, cur: dict) -> dict:
        """The config we'd want right now, given everything learnt. Pure function of stored state."""
        pins = set(self.store.pins(wid))
        eng = self._engine(wid)
        sched = self.store.get(f"sched:{wid}") or {}
        frozen = bool(pins & {"cohorts", "welcome_message", "voice", "caller_id", "schedule"})
        desired = copy.deepcopy(cur)
        if frozen:
            cohorts = [Cohort(c["id"], c.get("where") or {}) for c in cur.get("cohorts") or []]
        else:
            splits = self._splits(wid)
            while splits and partition_size(len(sched.get("values") or []), splits, sched.get("feature")) > S.MAX_COHORTS:
                splits = splits[:-1]
            cohorts = build_partition(sched.get("feature"), sched.get("values") or [], splits)
            desired["cohorts"] = [c.to_config() for c in cohorts]
        sf = self._split_features(wid)
        alloc: dict[str, dict] = {"default": {}}
        for dim in AGENT_DIMS:
            if dim in pins:
                alloc["default"][dim] = dict(dist(cur, "default", dim))
                for c in cohorts:
                    if dim in (cur["allocations"].get(c.id) or {}):
                        alloc.setdefault(c.id, {})[dim] = dict(cur["allocations"][c.id][dim])
                continue
            if dim == "caller_id":
                alloc["default"][dim] = callerid.target(self.store, wid, self.aggs[wid],
                                                        gated=not self.pol[wid].auto_allows(["caller_id"]))
                continue
            g = eng.allocation(dim, eng.statuses(dim, None, None))
            alloc["default"][dim] = g
            for c in cohorts:
                a = eng.allocation(dim, eng.statuses(dim, c.where, sf.get(dim)))
                if tv(a, g) > 1e-9:
                    alloc.setdefault(c.id, {})[dim] = a
        desired["allocations"] = alloc
        if "schedule" not in pins:
            desired["schedule"] = {"hour_weights": hour_weights_for(cohorts, sched),
                                   "lead_preferred_hour": dict((cur.get("schedule") or {}).get("lead_preferred_hour") or {})}
        # materiality: don't cut a new version for allocation moves nobody would notice
        if [c["id"] for c in desired.get("cohorts") or []] == [c["id"] for c in cur.get("cohorts") or []]:
            keys = ["default"] + [c.id for c in cohorts]
            for dim in AGENT_DIMS:
                if max(tv(dist(cur, k, dim), dist(desired, k, dim)) for k in keys) < S.NOOP_TV:
                    for k in keys:
                        src = cur["allocations"].get(k) or {}
                        tgt = desired["allocations"].setdefault(k, {})
                        if dim in src:
                            tgt[dim] = copy.deepcopy(src[dim])
                        else:
                            tgt.pop(dim, None)
            desired["allocations"] = {k: v for k, v in desired["allocations"].items() if v or k == "default"}
        return desired

    def _plan(self, wid: str, c: dict, protective: bool):
        cur, version = c["config"], c["version"]
        if any(i["kind"] == "hallucination" and (i["status"] in ("ready", "proposed") or
                                                 (i["status"] == "open" and self.now - i["opened_minute"] < 360))
               for i in self.store.incidents(wid, open_only=True)):
            return  # one thing at a time: the incident fix owns this workflow's approval budget
        desired = self.compose(wid, cur)
        dims = changed_dims(cur, desired)
        if not dims:
            if protective:
                self.store.put(f"protective:{wid}", None)
            return
        pol = self.pol[wid]
        busy = inflight(self.store, wid)
        auto_blocked = (self.store.get(f"auto_block:{wid}") or -10**9) > self.now - 1440
        if pol.auto_enabled and not auto_blocked:
            auto_dims = [d for d in dims if d in pol.allowed_dims]
            if auto_dims and (not busy or (protective and set(auto_dims) <= {"caller_id"})):
                partial = take_dims(cur, desired, auto_dims)
                if changed_dims(cur, partial):
                    stepped = step_toward(cur, partial, pol.max_shift)
                    if changed_dims(cur, stepped) and self._worth_it(wid, cur, stepped):
                        self._auto_apply(wid, version, cur, stepped, "protective" if protective else "routine")
                        return
        if busy:
            return
        rest = [d for d in dims if not pol.auto_allows([d]) or auto_blocked]
        if not rest:
            return
        purpose = "protective" if protective else "routine"
        ok, why = may_submit(pol, self.store, self.now, purpose)
        if not ok and purpose == "protective":
            ok, why = may_submit(pol, self.store, self.now, "routine")
            purpose = "routine" if ok else purpose
        if not ok or not self._worth_it(wid, cur, desired):
            return
        self._submit(wid, version, cur, desired, purpose)
        if protective:
            self.store.put(f"protective:{wid}", None)

    def _worth_it(self, wid: str, cur: dict, new: dict) -> bool:
        """Never ask for (or auto-apply) a change our own dry run says hurts the primary KPI or the guardrail."""
        dry = self._dry_run(wid, cur, new)["expected_relative_change"]
        obj = self.meta[wid]["objective"]
        primary = dry["engagement_rate" if obj["primary"] == "engagement_rate" else "pickup_rate"]
        g = obj.get("guardrail") or {}
        key, max_drop = next(iter(g.items())) if g else ("", 1.0)
        base = self.store.get(f"baseline:{wid}") or {}
        guard_rel = dry["pickup_rate" if key.startswith("pickup") else "engagement_rate"]
        guard_abs = guard_rel * (base.get("pickup" if key.startswith("pickup") else "engagement") or 0.5)
        if primary < -0.005 or guard_abs < -max_drop:
            last = self.store.get(f"skip_logged:{wid}") or -10**9
            if self.now - last >= 360:
                self.store.decide(wid, "proposal_skipped", f"not proposing: our dry run expects primary "
                                  f"{primary:+.1%}, guardrail {guard_abs:+.3f} — evidence disagrees with the rule "
                                  "that triggered it; waiting for more data", {"expected": dry,
                                                                              "dims": changed_dims(cur, new)})
                self.store.put(f"skip_logged:{wid}", self.now)
            return False
        return True

    # ================================================================== proposal content
    def _new_pid(self, wid, purpose) -> str:
        n = self.store.one("SELECT COUNT(*) FROM proposals")[0] + 1
        return f"{self.store.get('epoch')}-{wid}-{purpose}-{self.now}-{n}"

    def _affected(self, wid: str, cur: dict, new: dict) -> tuple[int, dict]:
        agg, m = self.aggs[wid], self.meta[wid]
        day = self.now // 1440
        active = agg.active_leads(day, len(m["cadence"]))
        ic = cohort_index(cur.get("cohorts") or [], self.vocab)
        inew = cohort_index(new.get("cohorts") or [], self.vocab)
        nc = ["default"] + [c["id"] for c in cur.get("cohorts") or []]
        nn = ["default"] + [c["id"] for c in new.get("cohorts") or []]
        hwc, hwn = (cur.get("schedule") or {}).get("hour_weights", {}), (new.get("schedule") or {}).get("hour_weights", {})
        changed = np.zeros(NCELL, dtype=bool)
        agent_changed = np.zeros(NCELL, dtype=bool)
        for i, j in {(int(a), int(b)) for a, b in zip(ic, inew)}:
            sel = (ic == i) & (inew == j)
            a_ch = any(tv(dist(cur, nc[i], d), dist(new, nn[j], d)) > 1e-6 for d in AGENT_DIMS)
            s_ch = (hwc.get(nc[i]) or hwc.get("default")) != (hwn.get(nn[j]) or hwn.get("default"))
            agent_changed[sel] = a_ch
            changed[sel] = a_ch or s_ch or cur.get("prompt_version") != new.get("prompt_version")
        upl = agg.uploaded.get(day) if agg.uploaded.get(day) is not None else agg.uploaded.get(day - 1)
        nxt = 0 if upl is None else int(upl[agent_changed].sum())
        now_n = int(active[changed].sum())
        if m.get("mid_flight") == "next_campaign_only":
            non_agent = cur.get("prompt_version") != new.get("prompt_version") or hwc != hwn
            n = int(active[changed & ~agent_changed].sum()) + nxt if non_agent else nxt
            return n, {"active_leads_affected": now_n, "next_batch_affected": nxt,
                       "note": "mid_flight=next_campaign_only: agent-facing changes reach new campaigns only"}
        return now_n, {"active_leads_affected": now_n, "next_batch_affected_est": nxt}

    def _dry_run(self, wid: str, cur: dict, new: dict) -> dict:
        agg, eng = self.aggs[wid], self._engine(wid)
        day = self.now // 1440
        active = agg.active_leads(day, len(self.meta[wid]["cadence"])).astype(float)
        if active.sum() == 0:
            active = np.ones(NCELL)
        ic = cohort_index(cur.get("cohorts") or [], self.vocab)
        inew = cohort_index(new.get("cohorts") or [], self.vocab)
        nc = ["default"] + [c["id"] for c in cur.get("cohorts") or []]
        nn = ["default"] + [c["id"] for c in new.get("cohorts") or []]
        num = den = 0.0
        per_dim_evidence = {}
        sf = self._split_features(wid)
        new_where = {c["id"]: c.get("where") or {} for c in new.get("cohorts") or []}
        cache: dict[tuple, dict] = {}
        all_cells = np.ones(NCELL, dtype=bool)

        def multipliers(dim: str, cohort: str) -> tuple[str, dict]:
            # estimate at the level the decision is made: the cohort's segment for this dim if it has
            # one, otherwise the whole workflow (per-cohort data is too thin and drifts out of date)
            f = sf.get(dim)
            vals = new_where.get(cohort, {}).get(f) if f else None
            key = (dim, f"{f}={vals[0]}") if vals and len(vals) == 1 else (dim, "all")
            if key not in cache:
                mask = self.vocab.mask({f: vals}) if key[1] != "all" else all_cells
                cache[key] = eng.relative_multipliers(dim, mask, day)
            return key[1], cache[key]

        for i, j in {(int(a), int(b)) for a, b in zip(ic, inew)}:
            sel = (ic == i) & (inew == j)
            w = float(active[sel].sum())
            if w <= 0:
                continue
            ratio = 1.0
            for dim in DIMS:
                a_new, a_cur = dist(new, nn[j], dim), dist(cur, nc[i], dim)
                if tv(a_new, a_cur) < 1e-6:
                    continue
                seg, mult = multipliers(dim, nn[j])
                rn = sum(p * mult[o]["mult"] for o, p in a_new.items())
                rc = sum(p * mult[o]["mult"] for o, p in a_cur.items())
                ratio *= rn / rc
                per_dim_evidence.setdefault(dim, {})[seg] = {o: mult[o] for o in sorted(mult)}
            num += w * ratio
            den += w
        eng_rel = num / den - 1 if den else 0.0
        # pickup: caller-ID mix (measured ratios) and call-time (history replay)
        pick_rel = 0.0
        did_ev = {}
        a_new, a_cur = dist(new, "default", "caller_id"), dist(cur, "default", "caller_id")
        if tv(a_new, a_cur) > 1e-6:
            W = callerid._window(agg, day, (self.now % 1440) // 60, 36)
            r = {}
            if W is not None and W[:, 0].sum() > 0:
                pooled = W[:, 1].sum() / W[:, 0].sum()
                for i, d in enumerate(agg.D):
                    r[d] = (W[i, 1] / W[i, 0]) / pooled if W[i, 0] >= 100 else 1.0
                    did_ev[d] = {"dials_36h": int(W[i, 0]), "pickup_ratio": round(r[d], 3)}
            rn = sum(p * r.get(o, 1.0) for o, p in a_new.items())
            rc = sum(p * r.get(o, 1.0) for o, p in a_cur.items())
            pick_rel += rn / rc - 1
        sched = self.store.get(f"sched:{wid}") or {}
        hw_c = (cur.get("schedule") or {}).get("hour_weights") or {}
        hw_n = (new.get("schedule") or {}).get("hour_weights") or {}
        if hw_n and not hw_c and sched.get("dry_run"):
            pick_rel += sched["dry_run"]["relative"]
        return {"method": "replay of observed per-arm / per-DID / per-hour rates on the currently active leads",
                "expected_relative_change": {"engagement_rate": round(eng_rel, 4), "pickup_rate": round(pick_rel, 4)},
                "arm_multipliers_used": per_dim_evidence, "caller_id": did_ev,
                "call_time_history_replay": sched.get("dry_run") if hw_n != hw_c else None,
                "honesty": "multipliers are shrunk toward 1 by their own uncertainty; unexplored options count as 1.0"}

    def _summary(self, wid, cur, new, dims) -> str:
        parts = []
        if "cohorts" in dims:
            sched = self.store.get(f"sched:{wid}") or {}
            parts.append(f"{len(new.get('cohorts') or [])} cohorts"
                         + (f" by {sched['feature']}" if sched.get("feature") else ""))
        names = {"welcome_message": "welcome", "voice": "voice", "caller_id": "caller ID"}
        for d in AGENT_DIMS:
            if d in dims:
                a = dist(new, "default", d)
                txt = "/".join(f"{o} {w:.0%}" for o, w in sorted(a.items(), key=lambda kv: -kv[1]))
                n_over = sum(1 for k, v in new["allocations"].items() if k != "default" and d in v)
                parts.append(f"{names[d]} {txt}" + (f" (+{n_over} cohort-specific)" if n_over else ""))
        if "schedule" in dims:
            parts.append("per-cohort call hours")
        if "prompt_version" in dims:
            parts.append(f"prompt {cur.get('prompt_version')}→{new.get('prompt_version')}")
        return "; ".join(parts)[:240]

    def _rationale(self, wid, dims) -> str:
        lines = []
        arms = self.store.arms(wid)
        for d in DIMS:
            if d not in dims and "cohorts" not in dims:
                continue
            for (dim, seg, opt), row in sorted(arms.items()):
                if dim != d or row["state"] == "explore":
                    continue
                ev = row.get("detail") or {}
                lines.append(f"{dim} {opt} [{seg}] → {row['state']} ({ev.get('reason')}): lift {ev.get('lift')}, "
                             f"z {ev.get('z')}, n {ev.get('n')} vs control n {ev.get('ctrl_n')}")
            exploring = [o for (dim, seg, o), r in arms.items() if dim == d and seg == "all" and r["state"] == "explore"]
            ctrl = (self.store.get(f"control:{wid}") or {}).get(d)
            if not arms or exploring:
                lines.append(f"{d}: testing challengers against {ctrl} on a capped share; winners need z≥"
                             f"{S.Z_WIN_GLOBAL} and ≥{S.MIN_CONN_DECIDE} connected calls per arm")
        if "caller_id" in dims:
            for did, r in self.store.dids(wid).items():
                ev = r.get("detail") or {}
                lines.append(f"caller ID {did}: {r['state']} ({ev.get('reason')}, ratio {ev.get('ratio')}, "
                             f"dials {ev.get('dials') or ev.get('history_dials')})")
        if "schedule" in dims or "cohorts" in dims:
            sched = self.store.get(f"sched:{wid}") or {}
            if sched.get("feature"):
                dr = sched["dry_run"]
                lines.append(f"call-time: {sched['feature']} explains the most hour-of-day pickup variation in history "
                             f"(signal {sched['signal']}); replay on {dr['history_dials']} historical dials projects "
                             f"pickup {dr['pickup_now']:.3f}→{dr['pickup_expected']:.3f}")
        return "\n".join(lines) or "configuration maintenance"

    def _body(self, wid, version, cur, new, purpose, extra=None) -> dict:
        dims = changed_dims(cur, new)
        affected, aff_detail = self._affected(wid, cur, new)
        dry = self._dry_run(wid, cur, new)
        dry["affected_detail"] = aff_detail
        primary = self.meta[wid]["objective"]["primary"]
        gain = dry["expected_relative_change"]["engagement_rate" if primary == "engagement_rate" else "pickup_rate"]
        impact = max(0.0, min(1.0, gain / S.IMPACT_FULL_SCALE))
        body = {"workflow_id": wid, "base_version": version, "proposed_config": new,
                "change_summary": f"[{purpose}] " + self._summary(wid, cur, new, dims),
                "diff": describe_diff(cur, new) or {"dims": dims}, "affected_leads": int(affected),
                "dry_run": dry, "impact_score": round(impact, 3),
                "rationale": self._rationale(wid, dims)}
        if extra:
            body.update(extra)
        return body

    # ================================================================== side effects (intent first)
    def _submit(self, wid, version, cur, new, purpose, extra=None) -> str | None:
        pol = self.pol[wid]
        body = self._body(wid, version, cur, new, purpose, extra)
        body["expires_in_hours"] = pol.ttl_hours
        pid = self._new_pid(wid, purpose)
        body["proposal_id"] = pid
        self.store.add_proposal({"proposal_id": pid, "workflow_id": wid, "path": "approval", "purpose": purpose,
                                 "status": "submitting", "base_version": version, "created_minute": self.now,
                                 "body": body})
        self.store.update_proposal(pid, submitted_minute=self.now)
        try:
            a = self.sim.request_approval(body)
            fault("after_submit_post")
        except ApiError as e:
            if e.code == "duplicate_proposal_id":
                self._reconcile()
                return pid
            self.store.update_proposal(pid, status="refused", reasons=[e.code, e.detail])
            self.store.decide(wid, "proposal_refused", f"simulator refused {pid}: {e.code}", {"detail": e.detail},
                              proposal_id=pid)
            if e.code == "stale_base_version":
                self.cfg.pop(wid, None)
            return None
        self.store.update_proposal(pid, status="pending", approval_id=a["approval_id"])
        self.store.decide(wid, "proposal_submitted", f"asked approver ({a['approval_id']}, {purpose}): "
                          f"{body['change_summary']}", {"approval_id": a["approval_id"], "impact_score":
                                                        body["impact_score"], "affected_leads": body["affected_leads"],
                                                        "dims": changed_dims(cur, new), "expires_at": a["expires_at"],
                                                        "rationale": body["rationale"]}, proposal_id=pid)
        return pid

    def _auto_apply(self, wid, version, cur, new, purpose):
        dims = changed_dims(cur, new)
        pid = self._new_pid(wid, "auto")
        rationale = self._rationale(wid, dims)
        dry = self._dry_run(wid, cur, new)
        body = {"proposal_id": pid, "base_version": version, "proposed_config": new, "rationale": rationale,
                "evidence": {"dry_run": dry, "purpose": purpose}}
        self.store.add_proposal({"proposal_id": pid, "workflow_id": wid, "path": "auto", "purpose": purpose,
                                 "status": "submitting", "base_version": version, "created_minute": self.now,
                                 "body": {**body, "change_summary": self._summary(wid, cur, new, dims),
                                          "diff": describe_diff(cur, new)}})
        try:
            r = self.sim.auto_apply(wid, body)
            fault("after_auto_post")
        except ApiError as e:
            if e.code == "duplicate_proposal_id":
                self._reconcile()
                return
            self.store.update_proposal(pid, status="refused", reasons=[e.code, e.detail])
            self.store.decide(wid, "auto_apply_refused", f"auto-apply refused ({e.code}); routing via approval",
                              {"detail": e.detail}, proposal_id=pid)
            if e.status == 403:
                self.store.put(f"auto_block:{wid}", self.now)
            self.cfg.pop(wid, None)
            return
        self.store.update_proposal(pid, status="applied", applied_version=r["version"], applied_minute=self.now)
        self.store.decide(wid, "auto_applied", f"auto-applied v{r['version']} ({purpose}, within policy: "
                          f"{', '.join(dims)}): {self._summary(wid, cur, new, dims)}",
                          {"version": r["version"], "dims": dims, "diff": describe_diff(cur, new),
                           "expected": dry["expected_relative_change"], "notice": "listed in the supervisor view"},
                          proposal_id=pid)
        self.store.record_version(wid, r["version"], "controller_auto", dims, pid, None, self.now, self.ts, new)

    def _process_inflight(self):
        for p in self.store.proposals(statuses=("pending", "approved")):
            if p["path"] != "approval" or not p["approval_id"]:
                continue
            wid, pid = p["workflow_id"], p["proposal_id"]
            a = self.sim.approval(p["approval_id"])
            s = a["status"]
            if s == "pending":
                continue
            if s == "approved":
                if p["status"] != "approved":
                    self.store.update_proposal(pid, status="approved", decided_minute=self.now)
                    self.store.decide(wid, "approval_approved", f"{a['approval_id']} approved at {a.get('decided_at')}"
                                      f"; applying (apply by {a.get('apply_by')})", a, proposal_id=pid)
                cur = self._config(wid)
                if p["purpose"] != "incident" and cur["version"] == p["base_version"] and \
                        not self._worth_it(wid, cur["config"], p["body"]["proposed_config"]):
                    # approval is permission, not obligation: the evidence moved against this change
                    self.store.update_proposal(pid, status="withdrawn", reasons=["evidence changed after approval"])
                    self.store.decide(wid, "approval_not_used", f"{a['approval_id']} approved but not applied: our "
                                      "dry run now expects it to hurt; letting it lapse", a, proposal_id=pid)
                    continue
                self._apply(p, a)
            elif s == "applied":
                hist = self.sim.config_history(wid)
                v = next((h for h in hist if h["approval_id"] == a["approval_id"]), {})
                self.store.update_proposal(pid, status="applied", applied_version=v.get("version"),
                                           applied_minute=self.now)
                self.store.decide(wid, "reconcile", f"{a['approval_id']} had been applied as v{v.get('version')} "
                                  f"(at {v.get('applied_at')}) before a crash; recorded now", v, proposal_id=pid)
                self._post_apply_incident_sync()
            else:
                self.store.update_proposal(pid, status=s, decided_minute=self.now, reasons=a.get("reasons"))
                self.store.decide(wid, f"approval_{s}", f"{a['approval_id']} {s}: {a.get('reasons') or ''}; "
                                  "will re-plan from fresh data at the next allowed slot", a, proposal_id=pid)
                self.store.alert("ticket", f"proposal_{s}", f"{wid}: proposal {pid} {s} {a.get('reasons') or ''}",
                                 wid, "Read the reasons; the controller re-plans automatically.")

    def _apply(self, p, a):
        wid, pid = p["workflow_id"], p["proposal_id"]
        try:
            r = self.sim.apply(wid, a["approval_id"])
            fault("after_apply_post")
        except ApiError as e:
            if e.code == "not_approved" and (e.detail or {}).get("status") == "applied":
                self.store.update_proposal(pid, status="applied")
                return
            status = {"stale_base_version": "stale", "approval_lapsed": "lapsed"}.get(e.code, "failed")
            self.store.update_proposal(pid, status=status, reasons=[e.code, e.detail])
            self.store.decide(wid, f"apply_{status}", f"could not apply {a['approval_id']}: {e.code} — "
                              "config moved since we proposed (re-proposing on the new base)", {"detail": e.detail},
                              proposal_id=pid)
            self.cfg.pop(wid, None)
            return
        self.store.update_proposal(pid, status="applied", applied_version=r["version"], applied_minute=self.now)
        cfg = p["body"]["proposed_config"]
        self.store.record_version(wid, r["version"], "controller_approved", r.get("changed_dims"), pid,
                                  a["approval_id"], self.now, self.ts, cfg)
        self.store.decide(wid, "applied", f"applied {a['approval_id']} as v{r['version']} "
                          f"({', '.join(r.get('changed_dims') or [])})", {"approval_id": a["approval_id"],
                                                                         "version": r["version"]}, proposal_id=pid)
        self._post_apply_incident_sync()

    # ================================================================== hallucination incidents (C8)
    def _post_apply_incident_sync(self):
        for inc in self.store.incidents(open_only=True):
            if inc["kind"] != "hallucination" or inc["status"] != "proposed":
                continue
            d = inc["detail"]
            p = self.store.proposal(d.get("proposal_id") or "")
            if p and p["status"] == "applied":
                d["applied_minute"] = p.get("applied_minute") or self.now
                self.store.update_incident(inc["id"], status="verifying", detail=d)
                self.store.decide(inc["workflow_id"], "incident_fix_applied",
                                  f"fix {d['fix']['prompt_version']} live; verifying on the next "
                                  f"{S.HALLUC_VERIFY_CONN} connected calls", d, proposal_id=p["proposal_id"])

    def _hallucination_step(self, wid: str, c: dict, st: dict):
        agg, cur = self.aggs[wid], c["config"]
        b0 = self.store.get(f"b0:{wid}") or 0.015
        prompt = cur["prompt_version"]
        open_ = [i for i in self.store.incidents(wid, open_only=True) if i["kind"] == "hallucination"]
        inc = open_[0] if open_ else None
        if inc is None:
            since = self._prompt_since(wid, prompt)
            spike = check_spike(agg, prompt, since, self.now, b0)
            if not spike:
                return
            iid = self.store.open_incident(wid, "hallucination", {"spike": spike, "prompt": prompt, "tried": [],
                                                                  "credits": 0})
            self.store.decide(wid, "incident_opened", f"hallucination spike on {prompt}: {spike['flagged']}/"
                              f"{spike['connected']} flagged ({spike['flag_rate']:.1%} vs baseline {b0:.1%}, "
                              f"p={spike['p_value']:.1e})", spike, subject=f"incident:{iid}")
            self.store.alert("page", "hallucination", f"{wid}: hallucination flags {spike['flag_rate']:.1%} vs "
                             f"{b0:.1%} on prompt {prompt}", wid,
                             "Controller is validating a fix; page only escalates if no fix is proposed within 2h. "
                             "Check `python -m controller view --workflow " + wid + "`.")
            inc = [i for i in self.store.incidents(wid, open_only=True) if i["id"] == iid][0]
        d = inc["detail"]
        if inc["status"] in ("open", "ready", "proposed") and prompt != d["prompt"]:
            # someone else changed the prompt; is the new one fine?
            since = self._prompt_since(wid, prompt)
            if not check_spike(agg, prompt, since, self.now, b0):
                pr = self.store.proposal(d.get("proposal_id") or "")
                by = "our fix" if pr and pr["status"] == "applied" else "a supervisor edit"
                if by == "our fix":
                    self._post_apply_incident_sync()
                    return
                self.store.update_incident(inc["id"], status="resolved", resolved_minute=self.now, detail=d)
                self.store.decide(wid, "incident_resolved", f"prompt changed to {prompt} by {by}; no spike on it",
                                  d)
                self.store.resolve_alert("hallucination", wid)
                return
        if inc["status"] == "open":
            self._incident_pick_fix(wid, inc, cur, b0)
            inc = next(i for i in self.store.incidents(wid) if i["id"] == inc["id"])
        if inc["status"] == "ready":
            self._incident_propose(wid, inc, c)
        elif inc["status"] == "proposed":
            p = self.store.proposal(d.get("proposal_id") or "")
            if p and p["status"] in ("rejected", "expired", "lapsed", "stale", "refused", "not_sent", "failed"):
                self.store.update_incident(inc["id"], status="ready", detail=d)
                self.store.decide(wid, "incident_reproposal", f"fix proposal {p['status']}; re-proposing with the "
                                  "same validation evidence on the current base", {"reasons": p.get("reasons")})
            elif p and p["status"] == "applied":
                self._post_apply_incident_sync()
            if self.now - inc["opened_minute"] > 120 and not (p and p["status"] in ("approved", "applied")):
                self.store.alert("page", "hallucination_unfixed", f"{wid}: hallucination incident open >2h without "
                                 "an applied fix", wid, "Check approver queue; consider manual prompt rollback.")
        elif inc["status"] == "verifying":
            fix = d["fix"]["prompt_version"]
            start = d.get("applied_minute") or self.now
            cn, en, fl = window_counts(agg, fix, start, self.now)
            if prompt != fix:
                return
            if cn >= S.HALLUC_VERIFY_CONN:
                p = poisson_sf(fl, b0 * cn)
                ok = p >= 1e-3 or fl / cn < 1.5 * b0
                base = self.store.get(f"baseline:{wid}") or {}
                r = ratio_test(en, cn, base.get("engagement", en / cn) * 10000, 10000)
                d["verification"] = {"connected": cn, "flag_rate": round(fl / cn, 4), "p_vs_baseline": p,
                                     "engagement": round(en / cn, 4), "engagement_vs_history": round(r.lift, 4)}
                if ok:
                    self.store.update_incident(inc["id"], status="resolved", resolved_minute=self.now, detail=d)
                    self.store.decide(wid, "incident_resolved", f"verified: {fix} flag rate {fl/cn:.1%} over {cn} calls "
                                      f"(baseline {b0:.1%}); engagement {en/cn:.1%} ({r.lift:+.1%} vs history)", d)
                    self.store.resolve_alert("hallucination", wid)
                    self.store.resolve_alert("hallucination_unfixed", wid)
                    if r.lift < -0.05 and r.z < -2.5:
                        self.store.alert("ticket", "fix_costs_engagement", f"{wid}: prompt {fix} is safe but "
                                         f"engagement is {r.lift:+.1%} vs history", wid, "Review prompt choice.")
                else:
                    d["tried"].append(fix)
                    self.store.update_incident(inc["id"], status="open", detail=d)
                    self.store.decide(wid, "incident_reopened", f"fix {fix} still flags {fl/cn:.1%}; trying another", d)

    def _prompt_since(self, wid, prompt) -> int:
        """When the current prompt went live; the business default counts as 'always'."""
        r = self.store.q("SELECT version, sim_minute, config FROM config_versions WHERE workflow_id=? ORDER BY version",
                         wid)
        since = -10**9
        prev = None
        for row in r:
            cfg = json.loads(row["config"]) if row["config"] else None
            pv = cfg.get("prompt_version") if cfg else None
            if pv is None:
                continue
            if pv == prompt and prev != prompt and prev is not None:
                since = row["sim_minute"] if row["sim_minute"] is not None else since
            elif pv != prompt:
                since = -10**9
            prev = pv
        return since

    def _incident_pick_fix(self, wid, inc, cur, b0):
        d = inc["detail"]
        pol = self.pol[wid]
        bar = max(pol.min_validation, 0) + S.VALIDATION_MARGIN
        cands = [c for c in proven_prompts(self.aggs[wid], b0, cur["prompt_version"]) if c["prompt_version"] not in d["tried"]]
        if not cands and not d.get("llm"):
            if d["credits"] + 3 > S.CREDIT_CAP_PER_INCIDENT or self.sim.state()["credits_remaining"] < 3:
                return self._incident_stuck(wid, inc, "credit cap reached before asking the LLM")
            sp = d["spike"]
            problem = (f"Hallucination flags at {sp['flag_rate']:.1%} of connected calls vs {b0:.1%} baseline since "
                       f"prompt {cur['prompt_version']} went live ({sp['flagged']}/{sp['connected']}). Suggest a safer "
                       "prompt that keeps engagement.")
            try:
                r = self.sim.suggest_fixes(wid, problem)
            except ApiError as e:
                return self._incident_stuck(wid, inc, f"LLM call failed: {e.code}")
            d["credits"] += 3
            d["llm"] = r["suggestions"]
            self.store.decide(wid, "incident_llm", f"asked LLM for fixes (3 credits): "
                              f"{[s['prompt_version'] for s in r['suggestions']]}", r)
        if not cands:
            cands = [{"prompt_version": s["prompt_version"], "summary": s["summary"], "source": "llm"}
                     for s in d.get("llm") or [] if s["prompt_version"] not in d["tried"]]
        for cand in cands:
            pv = cand["prompt_version"]
            cost = -(-S.VALIDATION_N // 100)
            if d["credits"] + cost > S.CREDIT_CAP_PER_INCIDENT or self.sim.state()["credits_remaining"] < cost:
                return self._incident_stuck(wid, inc, "credit cap reached during validation")
            try:
                v = self.sim.validate(wid, pv, S.VALIDATION_N)
            except ApiError as e:
                return self._incident_stuck(wid, inc, f"validation failed: {e.code}")
            d["credits"] += cost
            d["tried"].append(pv)
            passed = v["pass_rate"] >= bar
            self.store.decide(wid, "incident_validation", f"validated {pv} ({cand['source']}): pass rate "
                              f"{v['pass_rate']:.3f} on n={v['n']} vs our bar {bar:.3f} → "
                              f"{'candidate' if passed else 'rejected'}", {"candidate": cand, "validation": v})
            if passed:
                d["fix"] = {**cand, "validation": v}
                self.store.update_incident(inc["id"], status="ready", detail=d, credits_spent=d["credits"])
                return
        self.store.update_incident(inc["id"], detail=d, credits_spent=d["credits"])
        if not cands or all(c["prompt_version"] in d["tried"] for c in cands):
            if d.get("llm") and all(s["prompt_version"] in d["tried"] for s in d["llm"]):
                self._incident_stuck(wid, inc, "no candidate passed validation")

    def _incident_stuck(self, wid, inc, why):
        self.store.alert("page", "hallucination_no_fix", f"{wid}: cannot find a validated prompt fix ({why})", wid,
                         "Human decision needed: pick a prompt manually or pause the workflow.")
        self.store.decide(wid, "incident_stuck", why, inc["detail"])

    def _incident_propose(self, wid, inc, c):
        d = inc["detail"]
        pol = self.pol[wid]
        if inflight(self.store, wid, ("incident",)):
            return
        ok, why = may_submit(pol, self.store, self.now, "incident")
        if not ok:
            return
        cur = c["config"]
        new = copy.deepcopy(cur)
        new["prompt_version"] = d["fix"]["prompt_version"]
        sp, v = d["spike"], d["fix"]["validation"]
        cn, en, fl = window_counts(self.aggs[wid], cur["prompt_version"], sp["window_start_minute"], self.now)
        extra = {"evidence": {"validation_run_id": v["validation_run_id"]},
                 "impact_score": 1.0,
                 "change_summary": f"[incident] Roll prompt {cur['prompt_version']}→{new['prompt_version']}: "
                                   f"hallucination flags {fl}/{cn} ({fl / max(cn, 1):.1%}) vs {sp['baseline_rate']:.1%} normal",
                 "rationale": (f"Detected a hallucination spike on {cur['prompt_version']} (p={sp['p_value']:.1e}). "
                               f"{new['prompt_version']} is chosen because it has a {d['fix'].get('source')} in this "
                               f"workflow (flag rate {d['fix'].get('flag_rate', 'n/a')}, engagement "
                               f"{d['fix'].get('engagement', 'n/a')}) and passed validation at "
                               f"{v['pass_rate']:.3f} on {v['n']} synthetic conversations (policy minimum "
                               f"{pol.min_validation}). This replaces a supervisor edit; we ask rather than override."),
                 "dry_run": {"current_prompt": {"prompt": cur["prompt_version"], "connected": cn, "flagged": fl,
                                                "engagement": round(en / max(cn, 1), 4)},
                             "proposed_prompt": d["fix"], "validation": v}}
        pid = self._submit(wid, c["version"], cur, new, "incident", extra)
        if pid:
            d["proposal_id"] = pid
            self.store.update_incident(inc["id"], status="proposed", detail=d)

    # ================================================================== alerts
    def _alerts_sweep(self, st):
        cr = st.get("credits_remaining", 0)
        if cr < 10 and any(i["kind"] == "hallucination" for i in self.store.incidents(open_only=True)):
            self.store.alert("page", "credits_low", f"credits {cr} with an open incident", None,
                             "Top up credits or approve a manual prompt rollback.")
        for wid in self.meta:
            p = self.store.proposals(wid, ("approved",))
            for x in p:
                if (x.get("decided_minute") or self.now) < self.now - 60:
                    self.store.alert("page", "approved_not_applied", f"{wid}: {x['approval_id']} approved >60 min ago "
                                     "and not applied", wid, "Check controller logs for apply errors; apply window is "
                                     "2h.")
