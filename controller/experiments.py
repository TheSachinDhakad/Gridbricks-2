"""Welcome-message × voice experiments.

Design (SUBMISSION.md §5):
* Factorial: welcome and voice are randomised independently per call by the simulator, so each
  dimension is analysed as its own experiment with the other dimension averaged out.
* Every challenger is compared with the *control* (the business-default option) using only days on
  which both ran in the same population ("co-present days"): time trends, prompt changes and DID
  health shifts hit both arms equally, and an arm that never ran contributes nothing (stakeholders/05).
* Arm states (persisted, audited): explore → winner | dropped;  winner → decayed. Terminal states
  don't flap. Segment-level states ("age_band=60+") override the global state inside that segment.
* Winner: one-sided z ≥ 2.5 globally / 3.0 within a segment, ≥250 connected per arm, lift ≥ 3%,
  and the guardrail (pickup) not significantly breached. Harm: z ≤ −2 with ≥120 connected → stop.
* After promotion a 15% control holdout keeps measuring; the winner is rolled back when its lift
  over the last ~24h is significantly below control or significantly below its lift at promotion.
"""
from __future__ import annotations

import math

import numpy as np

from . import settings as S
from .aggregates import WFAgg
from .features import NCELL, Vocab, segments
from .stats import Ratio, diff_z, ratio_test, z_change

DIMS = ("welcome_message", "voice")


class ExperimentEngine:
    def __init__(self, store, wid: str, agg: WFAgg, vocab: Vocab, control: dict[str, str], max_drop: float):
        self.store, self.wid, self.agg, self.vocab = store, wid, agg, vocab
        self.control = control
        self.max_drop = max_drop

    # ------------------------------------------------------------------ data
    def options(self, dim: str) -> list[str]:
        return self.agg.W if dim == "welcome_message" else self.agg.V

    def _segments(self) -> list[tuple[str, np.ndarray]]:
        tot = None
        for d, a in self.agg.eng.items():
            s = a[:, :, :, 1].sum(axis=(1, 2))
            tot = s if tot is None else tot + s
        w = tot if tot is not None else np.ones(NCELL)
        segs = [("all", np.ones(NCELL, dtype=bool))]
        segs += [(f"{f}={v}", m) for f, v, m in segments(self.vocab, w, S.SEGMENT_MIN_SHARE)]
        return segs

    def _per_day(self, dim: str, segs) -> dict[int, np.ndarray]:
        """day -> (nSeg, nOpt, 3) [dials, connected, engaged]."""
        M = np.array([m for _, m in segs], dtype=np.float64)          # (nSeg, NCELL)
        out = {}
        axis = 2 if dim == "welcome_message" else 1
        for d, cube in self.agg.eng.items():
            marg = cube.sum(axis=axis)                                   # (NCELL, nOpt, 3)
            out[d] = (M @ marg.reshape(NCELL, -1)).reshape(len(segs), marg.shape[1], 3)
        return out

    @staticmethod
    def _pair(per_day: dict, s: int, o: int, c: int, days=None) -> tuple[np.ndarray, np.ndarray]:
        a = np.zeros(3)
        b = np.zeros(3)
        for d, X in per_day.items():
            if days is not None and d not in days:
                continue
            if X[s, o, 0] > 0 and X[s, c, 0] > 0:
                a += X[s, o]
                b += X[s, c]
        return a, b

    def compare(self, dim: str, seg_name: str, option: str, recent_from_day: int | None = None) -> dict:
        segs = self._segments()
        names = [n for n, _ in segs]
        if seg_name not in names:
            return {}
        pd_ = self._per_day(dim, segs)
        opts = self.options(dim)
        days = None if recent_from_day is None else {d for d in pd_ if d >= recent_from_day}
        a, b = self._pair(pd_, names.index(seg_name), opts.index(option), opts.index(self.control[dim]), days)
        return {"engagement": ratio_test(a[2], a[1], b[2], b[1]).brief(), "dials": int(a[0])}

    # ------------------------------------------------------------------ evaluation
    def evaluate(self, today: int, pinned: set[str], split_feature: dict[str, str | None],
                 can_split, pressure: bool = False) -> list[dict]:
        """Advance arm states. Returns the transitions made (already persisted + audited)."""
        transitions = []
        segs = self._segments()
        arms = self.store.arms(self.wid)
        for dim in DIMS:
            if dim in pinned:
                continue
            opts = self.options(dim)
            ctrl = self.control.get(dim)
            if ctrl not in opts or len(opts) < 2:
                continue
            ci = opts.index(ctrl)
            pd_ = self._per_day(dim, segs)
            recent = {d for d in pd_ if d >= today - 1}

            def stats(si, oi, days=None):
                a, b = self._pair(pd_, si, oi, ci, days)
                r = ratio_test(a[2], a[1], b[2], b[1])
                gd, gz = diff_z(a[1], a[0], b[1], b[0])
                return r, gd, gz

            def guard_ok(gd, gz):
                return not (-gd > self.max_drop and gz <= S.Z_GUARDRAIL)

            # ---- global
            cands = []
            have_winner = any(arms.get((dim, "all", o), {}).get("state") == "winner" for o in opts)
            for oi, o in enumerate(opts):
                if o == ctrl:
                    continue
                st = arms.get((dim, "all", o), {}).get("state", "explore")
                r, gd, gz = stats(0, oi)
                ev = {"window": "co-present days, all data", **r.brief(), "pickup_diff": round(gd, 4),
                      "pickup_z": round(gz, 2)}
                if st == "explore":
                    if min(r.n1, r.n0) >= S.MIN_CONN_HARM and r.z <= S.Z_HARM:
                        transitions.append(self._set(dim, "all", o, "dropped", "harm", ev,
                                                     f"stop {o}: engagement {r.lift:+.1%} vs {ctrl} (z={r.z:.1f})"))
                    elif not guard_ok(gd, gz) and min(r.n1, r.n0) >= S.MIN_CONN_HARM:
                        transitions.append(self._set(dim, "all", o, "dropped", "guardrail", ev,
                                                     f"stop {o}: pickup {gd:+.3f} breaches guardrail"))
                    elif (min(r.n1, r.n0) >= S.MIN_CONN_DECIDE and r.z >= S.Z_WIN_GLOBAL
                          and r.lift >= S.MIN_LIFT and guard_ok(gd, gz)):
                        cands.append((r.bound(-1.645), o, r, ev))
                    elif pressure and min(r.n1, r.n0) >= S.MIN_CONN_HARM and r.lift < 0:
                        transitions.append(self._set(dim, "all", o, "dropped", "guardrail_pressure", ev,
                                                     f"stop {o}: engagement {r.lift:+.1%} while the workflow's "
                                                     "engagement guardrail is under pressure"))
                    elif r.n1 >= S.FUTILITY_MIN_CONN and r.bound(1.645) - 1 < S.FUTILITY_UPPER:
                        transitions.append(self._set(dim, "all", o, "dropped", "futile", ev,
                                                     f"stop {o}: no worthwhile lift (90% upper {r.bound(1.645)-1:+.1%})"))
                elif st == "winner":
                    t = self._decay_check(dim, "all", o, arms[(dim, "all", o)], stats(0, oi, recent)[0], ev)
                    if t:
                        transitions.append(t)
            if cands and not have_winner:
                cands.sort(key=lambda x: -x[0])
                _, o, r, ev = cands[0]
                ev["promo"] = {"log_ratio": r.log_ratio, "se": r.se}
                transitions.append(self._set(dim, "all", o, "winner", "significant", ev,
                                             f"promote {o}: engagement {r.lift:+.1%} vs {ctrl} "
                                             f"(90% CI {r.bound(-1.645)-1:+.1%}..{r.bound(1.645)-1:+.1%}, z={r.z:.1f})"))
            # ---- segments (heterogeneity)
            arms = self.store.arms(self.wid)
            chosen = split_feature.get(dim)
            seg_cands: dict[str, list] = {}
            for si, (sname, _) in enumerate(segs):
                if si == 0:
                    continue
                feat = sname.split("=", 1)[0]
                if chosen and feat != chosen:
                    continue
                for oi, o in enumerate(opts):
                    if o == ctrl:
                        continue
                    gst = arms.get((dim, "all", o), {}).get("state", "explore")
                    sst = arms.get((dim, sname, o), {}).get("state")
                    r, gd, gz = stats(si, oi)
                    ev = {"window": "co-present days, all data", "segment": sname, **r.brief(),
                          "pickup_diff": round(gd, 4), "pickup_z": round(gz, 2)}
                    if sst is None and gst == "winner":
                        if min(r.n1, r.n0) >= 2 * S.MIN_CONN_HARM and r.z <= -2.5:
                            if can_split(dim, feat):
                                transitions.append(self._set(dim, sname, o, "excluded", "segment_harm", ev,
                                                             f"keep {o} away from {sname}: {r.lift:+.1%} (z={r.z:.1f})"))
                                split_feature[dim] = chosen = feat
                    elif sst is None and gst in ("explore", "dropped"):
                        if (min(r.n1, r.n0) >= S.MIN_CONN_DECIDE and r.z >= S.Z_WIN_SEGMENT
                                and r.lift >= S.MIN_LIFT and guard_ok(gd, gz)):
                            seg_cands.setdefault(sname, []).append((r.bound(-1.645), o, r, ev, feat))
                    elif sst == "winner":
                        rr = stats(si, oi, recent)[0]
                        t = self._decay_check(dim, sname, o, arms[(dim, sname, o)], rr, ev)
                        if t:
                            transitions.append(t)
            for sname, cs in sorted(seg_cands.items(), key=lambda kv: -max(c[0] for c in kv[1])):
                if any(arms.get((dim, sname, o), {}).get("state") == "winner" for o in opts):
                    continue
                cs.sort(key=lambda x: -x[0])
                _, o, r, ev, feat = cs[0]
                if chosen and feat != chosen:
                    continue
                if not can_split(dim, feat):
                    continue
                ev["promo"] = {"log_ratio": r.log_ratio, "se": r.se}
                transitions.append(self._set(dim, sname, o, "winner", "segment_significant", ev,
                                             f"promote {o} for {sname}: engagement {r.lift:+.1%} vs {ctrl} (z={r.z:.1f})"))
                split_feature[dim] = chosen = feat
        return transitions

    def _decay_check(self, dim, seg, o, row: dict, rr: Ratio, ev: dict) -> dict | None:
        promo = (row.get("detail") or {}).get("promo")
        if not promo or min(rr.n0, rr.n1) < S.DECAY_MIN_CONN:
            return None
        L, se = promo["log_ratio"], promo["se"]
        pr = Ratio(0, 0, 0, 0, L * L * L / (L * L + se * se), se)  # shrink: winner's curse inflates L
        zc = z_change(rr, pr)
        if rr.z <= S.DECAY_Z_RECENT or (rr.lift < 0 and zc <= S.DECAY_Z_CHANGE):
            ev = {**ev, "recent": rr.brief(), "lift_at_promotion": round(math.exp(promo["log_ratio"]) - 1, 4),
                  "z_change": round(zc, 2)}
            return self._set(dim, seg, o, "decayed", "decay", ev,
                             f"roll back {o}{'' if seg == 'all' else ' for ' + seg}: recent lift {rr.lift:+.1%} "
                             f"vs {math.exp(promo['log_ratio']) - 1:+.1%} at promotion (z_change={zc:.1f})")
        return None

    def _set(self, dim, seg, o, state, reason, ev, summary) -> dict:
        self.store.set_arm(self.wid, dim, seg, o, state, {"reason": reason, **ev})
        self.store.decide(self.wid, f"arm_{state}", summary, {"dim": dim, "segment": seg, "option": o,
                                                              "reason": reason, "evidence": ev},
                          subject=f"{dim}:{seg}:{o}")
        return {"dim": dim, "segment": seg, "option": o, "state": state, "reason": reason, "summary": summary,
                "protective": state in ("dropped", "decayed", "excluded") and reason != "futile"}

    # ------------------------------------------------------------------ allocation
    def statuses(self, dim: str, where: dict | None, split_feature: str | None) -> dict[str, str]:
        arms = self.store.arms(self.wid)
        opts = self.options(dim)
        out = {o: arms.get((dim, "all", o), {}).get("state", "explore") for o in opts}
        if where and split_feature and split_feature in where and len(where[split_feature]) == 1:
            seg = f"{split_feature}={where[split_feature][0]}"
            for o in opts:
                s = arms.get((dim, seg, o), {}).get("state")
                if s == "winner":
                    for o2 in opts:  # a segment winner outranks a global one inside the segment
                        if out[o2] == "winner":
                            out[o2] = "explore"
                    out[o] = "seg_winner"
                elif s in ("excluded", "decayed"):
                    out[o] = "dropped"
        return out

    def allocation(self, dim: str, statuses: dict[str, str]) -> dict[str, float]:
        opts = self.options(dim)
        ctrl = self.control[dim]
        ch = [o for o in opts if o != ctrl]
        if not ch:
            return {ctrl: 1.0}
        eps = min(S.EXPLORE_PER_ARM_MAX, S.EXPLORE_TOTAL / len(ch))
        winner = next((o for o in ch if statuses.get(o) == "seg_winner"), None) or \
            next((o for o in ch if statuses.get(o) == "winner"), None)
        explore = [o for o in ch if statuses.get(o) in ("explore",) and o != winner]
        a = {}
        if winner:
            a[winner] = 1.0 - S.HOLDOUT - eps * len(explore)
            a[ctrl] = S.HOLDOUT
        else:
            a[ctrl] = 1.0 - eps * len(explore)
        for o in explore:
            a[o] = eps
        return {o: round(w, 4) for o, w in a.items() if w > 0}

    # ------------------------------------------------------------------ dry run support
    def relative_multipliers(self, dim: str, mask: np.ndarray) -> dict[str, dict]:
        """Shrunk engagement multiplier of each option vs control inside `mask`, from all co-present data."""
        opts = self.options(dim)
        ci = opts.index(self.control[dim])
        segs = [("x", mask)]
        pd_ = self._per_day(dim, segs)
        out = {}
        for oi, o in enumerate(opts):
            if oi == ci:
                out[o] = {"mult": 1.0, "n": None}
                continue
            a, b = self._pair(pd_, 0, oi, ci)
            if a[1] < 30 or b[1] < 30:
                out[o] = {"mult": 1.0, "n": int(a[1])}
                continue
            r = ratio_test(a[2], a[1], b[2], b[1])
            k = r.log_ratio ** 2 / (r.log_ratio ** 2 + r.se ** 2)
            out[o] = {"mult": math.exp(r.log_ratio * k), "n": int(a[1]), "lift": round(r.lift, 4),
                      "z": round(r.z, 2)}
        return out
