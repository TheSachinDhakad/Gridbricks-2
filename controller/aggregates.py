"""Event ingestion into compact, idempotently rebuildable aggregates.

We never keep individual calls. Each call is folded into four small cubes per workflow and sim-day:

    eng[day]  (cell, welcome, voice, [dials, connected, engaged])   experiments, guardrails
    pick[day] (hour, cell, [dials, connected])                      call-time learning
    did[day]  (hour, caller_id, [dials, connected, engaged])        caller-ID health, daily KPIs
    prm[day]  (hour, prompt, [dials, connected, engaged, flagged])  hallucination detection

plus lead uploads / conclusions per cell (affected-lead counts, business outcome) and a
person -> cell array (the lead/feature join). For public_03_load this is ~45 MB in total.

Aggregates are a pure function of the ordered event stream, so crash safety is: snapshot
(aggregates + chunk watermark) atomically, and on restart replay only chunks after the watermark.
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np

from .features import NCELL, Vocab

_loads = json.loads


class WFAgg:
    def __init__(self, options: dict):
        self.W = list(options["welcome_message"])
        self.V = list(options["voice"])
        self.D = list(options["caller_id"])
        self.P = list(options["prompt_version"])
        self.Wi = {o: i for i, o in enumerate(self.W)}
        self.Vi = {o: i for i, o in enumerate(self.V)}
        self.Di = {o: i for i, o in enumerate(self.D)}
        self.Pi = {o: i for i, o in enumerate(self.P)}
        self.eng: dict[int, np.ndarray] = {}
        self.pick: dict[int, np.ndarray] = {}
        self.did: dict[int, np.ndarray] = {}
        self.prm: dict[int, np.ndarray] = {}
        self.uploaded: dict[int, np.ndarray] = {}
        self.concluded: dict[int, np.ndarray] = {}
        self.person_cell = np.full(4096, -1, dtype=np.int16)
        self.camp_day: dict[str, int] = {}
        self.orphan_calls = 0

    # ------------------------------------------------------------------ cubes
    def _cube(self, store: dict, day: int, shape) -> np.ndarray:
        a = store.get(day)
        if a is None:
            a = store[day] = np.zeros(shape, dtype=np.int32)
        return a

    def eng_day(self, d):
        return self._cube(self.eng, d, (NCELL, len(self.W), len(self.V), 3))

    def pick_day(self, d):
        return self._cube(self.pick, d, (24, NCELL, 2))

    def did_day(self, d):
        return self._cube(self.did, d, (24, len(self.D), 3))

    def prm_day(self, d):
        return self._cube(self.prm, d, (24, len(self.P), 4))

    def days(self) -> list[int]:
        return sorted(self.did)

    def sum_days(self, store: dict, days) -> np.ndarray | None:
        out = None
        for d in days:
            a = store.get(d)
            if a is not None:
                out = a.astype(np.int64) if out is None else out + a
        return out

    def ensure_person(self, n: int):
        if n >= len(self.person_cell):
            new = np.full(max(n + 1, 2 * len(self.person_cell)), -1, dtype=np.int16)
            new[: len(self.person_cell)] = self.person_cell
            self.person_cell = new

    def active_leads(self, today: int, cadence_days: int) -> np.ndarray:
        """Per-cell leads uploaded in campaigns still inside their cadence, minus those concluded."""
        out = np.zeros(NCELL, dtype=np.int64)
        for d in range(today - cadence_days + 1, today + 1):
            if d in self.uploaded:
                out += self.uploaded[d]
            if d in self.concluded:
                out -= self.concluded[d]
        return np.maximum(out, 0)

    def daily_kpis(self, day: int) -> dict:
        a = self.did.get(day)
        if a is None:
            return {"dials": 0, "connected": 0, "engaged": 0}
        s = a.sum(axis=(0, 1))
        return {"dials": int(s[0]), "connected": int(s[1]), "engaged": int(s[2])}


class Ingestor:
    """Parses NDJSON chunks and folds them into WFAgg cubes. Returns control-plane events."""

    def __init__(self, aggs: dict[str, WFAgg], vocab: Vocab, day0: dt.date):
        self.aggs = aggs
        self.vocab = vocab
        self.day0 = day0
        self._tc: dict[str, tuple[int, int]] = {}

    def _dh(self, ts: str) -> tuple[int, int]:
        k = ts[:13]
        r = self._tc.get(k)
        if r is None:
            d = (dt.date.fromisoformat(ts[:10]) - self.day0).days
            r = self._tc[k] = (d, int(ts[11:13]))
        return r

    def ingest(self, data: bytes) -> tuple[int, list[dict]]:
        aggs, vocab, dh = self.aggs, self.vocab, self._dh
        calls: dict[str, list] = {w: [] for w in aggs}
        concl: dict[str, list] = {w: [] for w in aggs}
        leads: dict[str, list] = {w: [] for w in aggs}
        control: list[dict] = []
        n = 0
        for raw in data.splitlines():
            if not raw:
                continue
            ev = _loads(raw)
            n += 1
            t = ev["type"]
            if t == "call":
                wf = ev["workflow_id"]
                a = aggs.get(wf)
                if a is None:
                    continue
                d, h = dh(ev["ts"])
                pid = ev["person_id"]
                var = ev["variant"]
                conn = ev["connected"]
                eng = ev["engaged"]
                qa = ev.get("qa")
                calls[wf].append((d, h, int(pid[pid.rindex(":p") + 2:]), a.Wi[var["welcome_message"]],
                                  a.Vi[var["voice"]], a.Di[var["caller_id"]], a.Pi[var["prompt_version"]],
                                  conn, eng, bool(qa and qa.get("hallucination_flag"))))
                if eng:
                    cd = a.camp_day.get(ev["campaign_id"])
                    if cd is not None:
                        concl[wf].append((cd, int(pid[pid.rindex(":p") + 2:])))
            elif t == "lead":
                wf = ev["workflow_id"]
                a = aggs.get(wf)
                if a is None:
                    continue
                pid = ev["person_id"]
                leads[wf].append((int(pid[pid.rindex(":p") + 2:]), vocab.cell(ev["features"]),
                                  a.camp_day.get(ev["campaign_id"], dh(ev["ts"])[0])))
            elif t == "campaign_created":
                a = aggs.get(ev["workflow_id"])
                if a is not None:
                    a.camp_day[ev["campaign_id"]] = dh(ev["ts"])[0]
                control.append(ev)
            else:
                control.append(ev)
        for wf, a in aggs.items():
            if leads[wf]:
                self._fold_leads(a, np.array(leads[wf], dtype=np.int64))
            if calls[wf]:
                self._fold_calls(a, np.array(calls[wf], dtype=np.int64))
            if concl[wf]:
                c = np.array(concl[wf], dtype=np.int64)
                a.ensure_person(int(c[:, 1].max()))
                cells = a.person_cell[c[:, 1]]
                for d in np.unique(c[:, 0]):
                    s = (c[:, 0] == d) & (cells >= 0)
                    arr = a.concluded.setdefault(int(d), np.zeros(NCELL, dtype=np.int32))
                    arr += np.bincount(cells[s], minlength=NCELL).astype(np.int32)
        return n, control

    @staticmethod
    def _fold_leads(a: WFAgg, L: np.ndarray):
        a.ensure_person(int(L[:, 0].max()))
        a.person_cell[L[:, 0]] = L[:, 1]
        for d in np.unique(L[:, 2]):
            s = L[:, 2] == d
            arr = a.uploaded.setdefault(int(d), np.zeros(NCELL, dtype=np.int32))
            arr += np.bincount(L[s, 1], minlength=NCELL).astype(np.int32)

    @staticmethod
    def _fold_calls(a: WFAgg, C: np.ndarray):
        day, hour, pn, w, v, d, p, conn, eng, flag = C.T
        a.ensure_person(int(pn.max()))
        cell = a.person_cell[pn].astype(np.int64)
        ok = cell >= 0
        a.orphan_calls += int((~ok).sum())
        nW, nV, nD, nP = len(a.W), len(a.V), len(a.D), len(a.P)
        for dd in np.unique(day):
            s = (day == dd) & ok
            if not s.any():
                continue
            dd = int(dd)
            c_, h_, w_, v_, d_, p_ = cell[s], hour[s], w[s], v[s], d[s], p[s]
            cn, en, fl = conn[s], eng[s], flag[s]
            # eng cube
            idx = ((c_ * nW + w_) * nV + v_) * 3
            cube = a.eng_day(dd).reshape(-1)
            sz = cube.size
            cube += np.bincount(idx, minlength=sz).astype(np.int32)
            cube += np.bincount(idx + 1, weights=cn, minlength=sz).astype(np.int32)
            cube += np.bincount(idx + 2, weights=en, minlength=sz).astype(np.int32)
            # pick cube
            idx = (h_ * NCELL + c_) * 2
            cube = a.pick_day(dd).reshape(-1)
            sz = cube.size
            cube += np.bincount(idx, minlength=sz).astype(np.int32)
            cube += np.bincount(idx + 1, weights=cn, minlength=sz).astype(np.int32)
            # did cube
            idx = (h_ * nD + d_) * 3
            cube = a.did_day(dd).reshape(-1)
            sz = cube.size
            cube += np.bincount(idx, minlength=sz).astype(np.int32)
            cube += np.bincount(idx + 1, weights=cn, minlength=sz).astype(np.int32)
            cube += np.bincount(idx + 2, weights=en, minlength=sz).astype(np.int32)
            # prompt cube
            idx = (h_ * nP + p_) * 4
            cube = a.prm_day(dd).reshape(-1)
            sz = cube.size
            cube += np.bincount(idx, minlength=sz).astype(np.int32)
            cube += np.bincount(idx + 1, weights=cn, minlength=sz).astype(np.int32)
            cube += np.bincount(idx + 2, weights=en, minlength=sz).astype(np.int32)
            cube += np.bincount(idx + 3, weights=fl, minlength=sz).astype(np.int32)
