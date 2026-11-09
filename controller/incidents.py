"""Hallucination incident detection and fix selection.

Detection is a Poisson tail test of the QA hallucination-flag count for the *current* prompt against
the workflow's own historical flag rate b0 (which already includes the detector's false positives):

    alarm  ⇔  n_connected ≥ 80  ∧  P(X ≥ x | λ = b0·n) < 1e-4  ∧  x/n ≥ 2·b0
              (1e-3 for a prompt that went live in the last 24h: the prior that it is the cause is high)

over two windows: since the prompt went live (capped at 24h) and the last 3h. With b0 ≈ 1.5% the
false-alarm probability per check is < 1e-4; ~40 checks/day/workflow → < 0.5% chance of one false
incident per workflow-day, while a 3-4× spike is caught within ~1-2 dialling hours.

A spike on a prompt with a long clean record that has *not* changed raises a ticket only: the
hypothesis "this prompt is bad" needs the prompt to have changed, and swapping a proven prompt for an
unproven one on a statistical fluke is the worst available action (it is how a "strict" script that
kills engagement gets shipped).

Fix choice is deterministic: a prompt with a production record in *this* workflow (≥500 connected
calls at a normal flag rate — usually the one the supervisor replaced) is preferred over anything the
LLM proposes; LLM suggestions are only requested when no proven prompt exists. Every candidate must
pass a validation run at our bar (policy minimum + margin) before it is proposed.
"""
from __future__ import annotations

from . import settings as S
from .aggregates import WFAgg
from .stats import poisson_sf


def flag_baseline(agg: WFAgg) -> tuple[float, int]:
    flags = conn = 0
    for d, a in agg.prm.items():
        if d < 0:
            s = a.sum(axis=(0, 1))
            conn += int(s[1])
            flags += int(s[3])
    # weak prior at 1.5% so a tiny history can't produce a silly baseline
    return (flags + 0.015 * 500) / (conn + 500), conn


def _hours(start_minute: int, end_minute: int):
    m = (start_minute // 60) * 60
    while m <= end_minute:
        d, mod = divmod(m, 1440)
        yield d, mod // 60
        m += 60


def window_counts(agg: WFAgg, prompt: str, start: int, end: int) -> tuple[int, int, int]:
    """(connected, engaged, flagged) for `prompt` over [start, end] at hour granularity."""
    pi = agg.Pi.get(prompt)
    if pi is None:
        return 0, 0, 0
    c = e = f = 0
    for d, h in _hours(start, end):
        a = agg.prm.get(d)
        if a is not None:
            c += int(a[h, pi, 1])
            e += int(a[h, pi, 2])
            f += int(a[h, pi, 3])
    return c, e, f


def check_spike(agg: WFAgg, prompt: str, prompt_since: int, now: int, b0: float) -> dict | None:
    new_prompt = now - prompt_since < 1440
    for name, start in (("since_prompt_live", max(prompt_since, now - 1440)), ("last_3h", now - S.HALLUC_WINDOW_MIN)):
        c, e, f = window_counts(agg, prompt, start, now)
        if c < S.HALLUC_MIN_CONN:
            continue
        p = poisson_sf(f, b0 * c)
        # a prompt that just changed is the prime suspect, so it needs less evidence to alarm
        thr = S.HALLUC_P_ALARM_NEW_PROMPT if (new_prompt and name == "since_prompt_live") else S.HALLUC_P_ALARM
        if p < thr and f / c >= S.HALLUC_MIN_RATIO * b0:
            return {"window": name, "prompt": prompt, "connected": c, "flagged": f, "flag_rate": round(f / c, 4),
                    "baseline_rate": round(b0, 4), "p_value": p, "window_start_minute": start}
    return None


def prompt_record(agg: WFAgg, prompt: str, before_minute: int) -> tuple[int, int]:
    """(connected, flagged) for `prompt` strictly before `before_minute` — its clean history, if any."""
    pi = agg.Pi.get(prompt)
    if pi is None:
        return 0, 0
    bd, bh = divmod(before_minute // 60, 24)
    c = f = 0
    for d, a in agg.prm.items():
        if d < bd:
            c += int(a[:, pi, 1].sum())
            f += int(a[:, pi, 3].sum())
        elif d == bd:
            c += int(a[:bh, pi, 1].sum())
            f += int(a[:bh, pi, 3].sum())
    return c, f


def proven_prompts(agg: WFAgg, b0: float, exclude: str) -> list[dict]:
    out = []
    tot = {}
    for a in agg.prm.values():
        s = a.sum(axis=0)  # (nP, 4)
        for i, p in enumerate(agg.P):
            t = tot.setdefault(p, [0, 0, 0])
            t[0] += int(s[i, 1])
            t[1] += int(s[i, 2])
            t[2] += int(s[i, 3])
    for p, (c, e, f) in tot.items():
        if p == exclude or c < 500:
            continue
        rate = f / c
        if rate <= 1.5 * b0:
            out.append({"prompt_version": p, "connected": c, "flag_rate": round(rate, 4),
                        "engagement": round(e / c, 4), "source": "production record"})
    out.sort(key=lambda x: -x["connected"])
    return out
