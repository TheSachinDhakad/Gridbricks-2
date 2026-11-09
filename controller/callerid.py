"""Caller-ID (DID) health: detect degradation, rotate, explore unknown numbers safely.

Caller IDs are randomised per call independently of hour and cohort, so a DID's pickup rate can be
compared directly with the pooled pickup of the other healthy DIDs over the same hours. We act on
ratios over windows of hundreds of dials, never on single calls.

States (persisted): healthy | unknown | bad
  * established DIDs (seen in history) start healthy; never-used DIDs start unknown
  * bad      : ratio < 0.75 (0.60 for a number already in rotation) with z ≤ −4 / −3.5 / −3 over the last
               2 / 6 / 36 dialling hours; a number in rotation must *also* have dropped vs. its own pickup
               in the same hours on the previous two days (a flag is sudden; load is gradual).
               Or: an engagement guardrail breach.
  * unknown→healthy : ≥250 dials and the lower 90% bound of the ratio ≥ 0.85
Target allocation: healthy DIDs share traffic equally (spreading volume is what keeps a number off
spam lists); up to two unknown DIDs get a small exploration share; bad DIDs get nothing.
"""
from __future__ import annotations

import numpy as np

from . import settings as S
from .aggregates import WFAgg
from .stats import diff_z, ratio_test


def _window(agg: WFAgg, day: int, hour: int, n_hours: int, with_hours: bool = False):
    """Sum of the DID cube over the last `n_hours` hours that had any dials (up to and incl. now)."""
    out, got, hours = None, 0, []
    d, h = day, hour
    for _ in range(24 * 6):
        a = agg.did.get(d)
        if a is not None and a[h, :, 0].sum() > 0:
            out = a[h].astype(np.int64) if out is None else out + a[h]
            hours.append((d, h))
            got += 1
            if got >= n_hours:
                break
        h -= 1
        if h < 0:
            d, h = d - 1, 23
    return (out, hours) if with_hours else out


def _same_hours_before(agg: WFAgg, hours, days_back=(1, 2)) -> np.ndarray | None:
    out = None
    for d, h in hours:
        for k in days_back:
            a = agg.did.get(d - k)
            if a is not None:
                out = a[h].astype(np.int64) if out is None else out + a[h]
    return out


def evaluate(store, wid: str, agg: WFAgg, day: int, hour: int, max_drop_eng: float) -> list[dict]:
    states = store.dids(wid)
    trans = []
    short, short_hours = _window(agg, day, hour, S.DID_WINDOW_HOURS, with_hours=True)
    long_ = _window(agg, day, hour, 36)
    if short is None:
        return trans
    fast, fast_hours = _window(agg, day, hour, 2, with_hours=True)
    # shorter windows are checked more often on less data, so they need stronger evidence
    windows = [("2h", fast, _same_hours_before(agg, fast_hours), -4.0),
               ("6h", short, _same_hours_before(agg, short_hours), -3.5), ("36h", long_, None, S.DID_BAD_Z)]
    healthy = [d for d in agg.D if states.get(d, {}).get("state") == "healthy"]
    for i, did in enumerate(agg.D):
        row = states.get(did, {})
        st = row.get("state", "unknown")
        if st == "bad":
            if S.DID_REPROBE_HOURS and store.clock()[0] - row["since_minute"] >= S.DID_REPROBE_HOURS * 60:
                trans.append(_set(store, wid, did, "unknown", "reprobe", {"previous": row.get("detail")},
                                  f"caller ID {did}: {S.DID_REPROBE_HOURS}h since it was rotated out — "
                                  "re-exploring it on a small share"))
            continue
        bad_ratio = S.DID_BAD_RATIO_ESTABLISHED if st == "healthy" else S.DID_BAD_RATIO
        others = [agg.Di[x] for x in healthy if x != did]
        if not others:  # e.g. a single established number: compare with whatever else is in use
            others = [agg.Di[x] for x in agg.D
                      if x != did and states.get(x, {}).get("state", "unknown") != "bad"]
        if not others:
            continue
        for name, W, past, zthr in windows:
            if W is None:
                continue
            n, c = W[i, 0], W[i, 1]
            on, oc = W[others, 0].sum(), W[others, 1].sum()
            if n < S.DID_MIN_DIALS_BAD or on < S.DID_MIN_DIALS_BAD:
                continue
            r = ratio_test(c, n, oc, on)
            if r.ratio < bad_ratio and r.z <= zthr:
                ev = {"window": name, "pickup": round(c / n, 4), "others_pickup": round(oc / on, 4),
                      "ratio": round(r.ratio, 3), "z": round(r.z, 2), "dials": int(n)}
                if st == "healthy":
                    # a number already in rotation must also have dropped vs its own recent past (same hours):
                    # a flag is sudden, while plain load makes a number steadily worse than fresh ones
                    if past is None or past[i, 0] < S.DID_MIN_DIALS_BAD:
                        continue
                    own = ratio_test(c, n, past[i, 1], past[i, 0])
                    ev["vs_own_past"] = {"ratio": round(own.ratio, 3), "z": round(own.z, 2), "past_dials": int(past[i, 0])}
                    if not (own.ratio < S.DID_BAD_RATIO and own.z <= S.DID_BAD_Z):
                        continue
                trans.append(_set(store, wid, did, "bad", "pickup_degraded", ev,
                                  f"caller ID {did} degraded: pickup {c/n:.1%} vs {oc/on:.1%} on other numbers "
                                  f"({n} dials, last {name}) — rotating it out"))
                break
        else:
            if long_ is not None:
                n, c, e = long_[i]
                on, oc, oe = long_[others].sum(0)
                if c >= 100 and oc >= 100:
                    dd, dz = diff_z(e, c, oe, oc)
                    if -dd > max_drop_eng and dz <= -3.0:
                        trans.append(_set(store, wid, did, "bad", "engagement_guardrail",
                                          {"engagement": round(e / c, 4), "others": round(oe / oc, 4), "z": round(dz, 2)},
                                          f"caller ID {did}: engagement {e/c:.1%} vs {oe/oc:.1%} breaches guardrail"))
                        continue
                if st == "unknown" and n >= S.DID_HEALTHY_MIN_DIALS and on >= S.DID_HEALTHY_MIN_DIALS:
                    r = ratio_test(c, n, oc, on)
                    ev = {"window": "36h", "pickup": round(c / n, 4), "others_pickup": round(oc / on, 4),
                          "ratio": round(r.ratio, 3), "lo90": round(r.bound(-1.645), 3), "dials": int(n)}
                    if r.bound(-1.645) >= S.DID_HEALTHY_LOWER:
                        trans.append(_set(store, wid, did, "healthy", "explored_ok", ev,
                                          f"caller ID {did} healthy after exploration: pickup ratio {r.ratio:.2f} "
                                          f"(90% lower {r.bound(-1.645):.2f}) — adding it to rotation"))
                    elif n >= 4 * S.DID_HEALTHY_MIN_DIALS and r.bound(1.645) < 0.95:
                        trans.append(_set(store, wid, did, "bad", "explored_weak", ev,
                                          f"caller ID {did} consistently weaker (ratio {r.ratio:.2f}) — not used"))
    return trans


def target(store, wid: str, agg: WFAgg, gated: bool) -> dict[str, float]:
    states = store.dids(wid)
    healthy = [d for d in agg.D if states.get(d, {}).get("state") == "healthy"]
    unknown = [d for d in agg.D if states.get(d, {}).get("state", "unknown") == "unknown"][: S.DID_MAX_EXPLORING]
    eps = S.DID_EXPLORE_GATED if gated else S.DID_EXPLORE_AUTO
    if not healthy:
        if unknown:
            return {d: round(1 / len(unknown), 4) for d in unknown}
        # everything is bad: keep the least-bad number rather than stopping calls (alerted separately)
        best = max(agg.D, key=lambda d: (states.get(d, {}).get("detail") or {}).get("ratio", 0))
        return {best: 1.0}
    a = {d: eps for d in unknown}
    rest = 1.0 - eps * len(unknown)
    for d in healthy:
        a[d] = rest / len(healthy)
    return {d: round(w, 4) for d, w in a.items() if w > 0}


def _set(store, wid, did, state, reason, ev, summary) -> dict:
    store.set_did(wid, did, state, {"reason": reason, **ev})
    store.decide(wid, f"did_{state}", summary, {"did": did, "reason": reason, "evidence": ev}, subject=f"caller_id:{did}")
    return {"did": did, "state": state, "reason": reason, "summary": summary, "protective": state == "bad"}
