"""Call-time optimisation (per cohort) and the cohort partition.

Call time. The dialler decides *who* to call in each hour by weight. Pickup depends on a person's
daily rhythm, which correlates with their features. From history (and later live data) we estimate,
for each value v of a candidate feature f and each hour h, the *comparative advantage*

        a[v,h] = pickup(v, h) / pickup(all, h)

(shrunk toward 1 with a prior of SCHED_PRIOR_DIALS dials). Dividing by the hour's overall rate
cancels effects common to everyone in that hour (e.g. later hours being dominated by retries of
hard-to-reach leads). The feature whose values differ most — Σ dials·ln(a)² — becomes the scheduling
feature, and each value's hour table is clip(a^β). No hour gets weight 0, so capacity is never left
unused. Per-person preferred hours were considered and cut (SUBMISSION.md §2, C4).

Partition. Cohorts = scheduling feature values × (at most one heterogeneity split per experiment
dimension). This is the single cohort list used by the config, the experiments and the view.
"""
from __future__ import annotations

import itertools

import numpy as np

from . import settings as S
from .aggregates import WFAgg
from .features import FEATURES, Cohort, Vocab, slug

SHORT = {"lang": "lang", "city_tier": "tier", "age_band": "age", "value_band": "value"}


def learn_schedule(agg: WFAgg, vocab: Vocab, days: list[int], window: tuple[int, int]) -> dict | None:
    """Pick the scheduling feature and hour weights from the pickup cube over `days`."""
    P = agg.sum_days(agg.pick, days)
    if P is None:
        return None
    lo, hi = window
    hours = list(range(lo, hi))
    P = P[hours]                                  # (H, NCELL, 2)
    dials_h = P[:, :, 0].sum(1).astype(float)
    conn_h = P[:, :, 1].sum(1).astype(float)
    if dials_h.sum() < 2000:
        return None
    r_h = np.where(dials_h > 0, conn_h / np.maximum(dials_h, 1), conn_h.sum() / dials_h.sum())
    codes = vocab.cell_codes()
    best = None
    tot_d = float(P[:, :, 0].sum())
    for f in FEATURES:
        vals = [(v, i) for v, i in vocab.index[f].items()]
        if not 2 <= len(vals) <= S.SCHED_MAX_VALUES:
            continue
        keep, A, D = [], [], []
        for v, i in vals:
            m = codes[f] == i
            d = P[:, m, 0].sum(1).astype(float)
            c = P[:, m, 1].sum(1).astype(float)
            if d.sum() / tot_d < 0.02:
                continue
            rate = (c + S.SCHED_PRIOR_DIALS * r_h) / (d + S.SCHED_PRIOR_DIALS)
            keep.append(v)
            A.append(rate / np.maximum(r_h, 1e-9))
            D.append(d)
        if len(keep) < 2:
            continue
        A, D = np.array(A), np.array(D)
        score = float((D * np.log(A) ** 2).sum() / D.sum())
        if best is None or score > best[0]:
            best = (score, f, keep, A, D)
    if best is None or best[0] < S.SCHED_MIN_SIGNAL:
        return {"feature": None, "signal": None if best is None else round(best[0], 5)}
    score, f, keep, A, D = best
    # time-matching only: each cohort's dial-weighted mean advantage is 1, so we change *when* a cohort is
    # called, not *whether* it is favoured over another cohort across the day (fairness, guardrail).
    A_t = A / ((D * A).sum(1, keepdims=True) / np.maximum(D.sum(1, keepdims=True), 1))
    W = np.clip(A_t ** S.SCHED_BETA, S.SCHED_W_MIN, S.SCHED_W_MAX)
    weights = {v: {str(h): round(float(W[k, j]), 2) for j, h in enumerate(hours)} for k, v in enumerate(keep)}
    # dry run on the same history: expected pickup if each hour's dialled mix were re-weighted
    base = float(conn_h.sum() / dials_h.sum())
    rates = A * r_h[None, :]                      # (V, H)
    mix_new = D * W
    mix_new = mix_new / np.maximum(mix_new.sum(0, keepdims=True), 1e-9)
    exp_new = float((mix_new * rates).sum(0) @ dials_h / dials_h.sum())
    peak = {v: [h for _, h in sorted(((-W[k, j], h) for j, h in enumerate(hours)))[:3]] for k, v in enumerate(keep)}
    return {"feature": f, "values": keep, "weights": weights, "signal": round(score, 5),
            "dry_run": {"history_dials": int(dials_h.sum()), "pickup_now": round(base, 4),
                        "pickup_expected": round(exp_new, 4), "relative": round(exp_new / base - 1, 4),
                        "best_hours": peak,
                        "caveat": "assumes each hour's eligible pool has the historical mix; ignores depletion"}}


# --------------------------------------------------------------------------- partition
def build_partition(sched_feature: str | None, sched_values: list[str], splits: list[tuple[str, list[list[str]]]]
                    ) -> list[Cohort]:
    """Ordered, first-match cohort list.

    `splits` = [(feature, [value-group, ...])], each group becoming its own cell; leads outside every
    group fall through to the base cell. Cells are emitted most-specific first so first-match works.
    """
    splits = [(f, groups) for f, groups in splits if f != sched_feature and groups]
    base = [(sched_feature, v) for v in sched_values] if sched_feature else [(None, None)]
    out: list[Cohort] = []
    for bf, bv in base:
        # every combination of (one group or "rest") per split, most specific first
        options = [[(f, g) for g in groups] + [None] for f, groups in splits]
        combos = list(itertools.product(*options)) if options else [()]
        combos.sort(key=lambda c: -sum(x is not None for x in c))
        for combo in combos:
            where, parts = {}, []
            if bf:
                where[bf] = [bv]
                parts.append(f"{SHORT[bf]}_{slug(bv)}")
            for x in combo:
                if x is None:
                    continue
                f, g = x
                where[f] = list(g)
                parts.append(f"{SHORT[f]}_{slug('_'.join(g))}")
            if not where:
                continue
            out.append(Cohort(id="__".join(parts), where=where))
    return out


def partition_size(n_sched: int, splits: list[tuple[str, list[list[str]]]], sched_feature) -> int:
    k = max(n_sched, 1)
    for f, groups in splits:
        if f != sched_feature:
            k *= len(groups) + 1
    return k - (0 if n_sched else 1)


def hour_weights_for(cohorts: list[Cohort], sched: dict | None) -> dict:
    if not sched or not sched.get("feature"):
        return {}
    f = sched["feature"]
    out = {}
    for c in cohorts:
        vals = c.where.get(f)
        if vals and len(vals) == 1 and vals[0] in sched["weights"]:
            out[c.id] = dict(sched["weights"][vals[0]])
    return out

