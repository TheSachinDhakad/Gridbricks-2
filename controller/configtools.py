"""Workflow-config helpers that mirror the documented contract (docs/SIMULATOR.md §3–4).

These re-implement *documented* semantics (resolution of a cohort's distribution, changed dims,
total-variation shift) so the controller can check a change against policy before sending it. They
do not import or read the simulator.
"""
from __future__ import annotations

import copy

AGENT_DIMS = ("welcome_message", "voice", "caller_id")
CHANGE_DIMS = ("cohorts", "welcome_message", "voice", "caller_id", "prompt_version", "schedule")


def norm(d: dict) -> dict:
    s = float(sum(v for v in d.values() if v > 0))
    return {k: v / s for k, v in d.items() if v > 0} if s > 0 else {}


def dist(cfg: dict, cohort: str, dim: str) -> dict:
    return norm((cfg["allocations"].get(cohort) or {}).get(dim) or cfg["allocations"]["default"][dim])


def tv(a: dict, b: dict) -> float:
    a, b = norm(a), norm(b)
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in set(a) | set(b))


def cohort_ids(cfg: dict) -> list[str]:
    return [c["id"] for c in cfg.get("cohorts") or []]


def _sched(cfg: dict) -> dict:
    s = cfg.get("schedule") or {}
    hw = {k: {str(h): float(w) for h, w in (v or {}).items()} for k, v in (s.get("hour_weights") or {}).items()}
    return {"hour_weights": hw, "lead_preferred_hour": dict(s.get("lead_preferred_hour") or {})}


def same_schedule(old: dict, new: dict, tol: float = 1e-6) -> bool:
    so, sn = _sched(old), _sched(new)
    if so["lead_preferred_hour"] != sn["lead_preferred_hour"] or set(so["hour_weights"]) != set(sn["hour_weights"]):
        return False
    for k, a in so["hour_weights"].items():
        b = sn["hour_weights"][k]
        if set(a) != set(b) or any(abs(a[h] - b[h]) > tol for h in a):
            return False
    return True


def changed_dims(old: dict, new: dict, tol: float = 1e-6) -> list[str]:
    ch = []
    if [(c["id"], c.get("where")) for c in old.get("cohorts") or []] != \
            [(c["id"], c.get("where")) for c in new.get("cohorts") or []]:
        ch.append("cohorts")
    keys = {"default"} | set(old["allocations"]) | set(new["allocations"]) | set(cohort_ids(old)) | set(cohort_ids(new))
    for dim in AGENT_DIMS:
        if any(tv(dist(old, k, dim), dist(new, k, dim)) > tol for k in keys):
            ch.append(dim)
    if old.get("prompt_version") != new.get("prompt_version"):
        ch.append("prompt_version")
    if not same_schedule(old, new, tol):
        ch.append("schedule")
    return [d for d in CHANGE_DIMS if d in ch]


def max_shift(old: dict, new: dict) -> float:
    keys = {"default"} | set(cohort_ids(old)) | set(cohort_ids(new))
    return max((tv(dist(old, k, d), dist(new, k, d)) for k in keys for d in AGENT_DIMS), default=0.0)


def step_toward(cur: dict, tgt: dict, limit: float) -> dict:
    """Move agent-dim allocations from cur toward tgt by at most `limit` TV (one tick's worth).

    Requires identical cohorts. Non-agent dims are taken from tgt as-is.
    """
    sh = max_shift(cur, tgt)
    if sh <= limit + 1e-12:
        return copy.deepcopy(tgt)
    alpha = 0.98 * limit / sh
    out = copy.deepcopy(tgt)
    keys = ["default"] + cohort_ids(cur)
    for k in keys:
        for d in AGENT_DIMS:
            a, b = dist(cur, k, d), dist(tgt, k, d)
            explicit = k == "default" or d in (cur["allocations"].get(k) or {}) or d in (tgt["allocations"].get(k) or {})
            if not explicit:
                continue
            m = {o: round(a.get(o, 0) + alpha * (b.get(o, 0) - a.get(o, 0)), 4) for o in set(a) | set(b)}
            out["allocations"].setdefault(k, {})[d] = {o: w for o, w in sorted(m.items()) if w > 0}
    return out


def take_dims(cur: dict, desired: dict, dims) -> dict:
    """cur with only `dims` taken from desired, keeping cur's cohorts (for auto-apply subsets)."""
    out = copy.deepcopy(cur)
    ids = set(cohort_ids(cur))
    for d in dims:
        if d in AGENT_DIMS:
            for k in ["default"] + cohort_ids(cur):
                src = k if (k == "default" or k in cohort_ids(desired)) else "default"
                want = dist(desired, src, d)
                if k == "default" or d in (desired["allocations"].get(k) or {}) or d in (cur["allocations"].get(k) or {}):
                    out["allocations"].setdefault(k, {})[d] = want
        elif d == "schedule":
            s = _sched(desired)
            out["schedule"] = {"hour_weights": {k: v for k, v in s["hour_weights"].items() if k == "default" or k in ids},
                               "lead_preferred_hour": s["lead_preferred_hour"]}
        elif d == "prompt_version":
            out["prompt_version"] = desired["prompt_version"]
    return out


def describe_diff(old: dict, new: dict) -> dict:
    out = {}
    co = {c["id"]: c.get("where") for c in old.get("cohorts") or []}
    cn = {c["id"]: c.get("where") for c in new.get("cohorts") or []}
    if list(co.items()) != list(cn.items()):
        out["cohorts"] = {"added": {k: v for k, v in cn.items() if k not in co},
                          "removed": sorted(k for k in co if k not in cn),
                          "order": list(cn)}
    keys = ["default"] + list(cn)
    for d in AGENT_DIMS:
        per = {}
        for k in keys:
            a = dist(old, k if k in co or k == "default" else "default", d)
            b = dist(new, k, d)
            if tv(a, b) > 1e-6:
                per[k] = {"from": {o: round(w, 3) for o, w in sorted(a.items())},
                          "to": {o: round(w, 3) for o, w in sorted(b.items())}}
        if per:
            out[d] = per
    if old.get("prompt_version") != new.get("prompt_version"):
        out["prompt_version"] = {"from": old.get("prompt_version"), "to": new.get("prompt_version")}
    so, sn = _sched(old), _sched(new)
    if so != sn:
        out["schedule"] = {"hour_weights": {k: v for k, v in sn["hour_weights"].items()
                                            if so["hour_weights"].get(k) != v},
                           "removed_tables": sorted(set(so["hour_weights"]) - set(sn["hour_weights"])),
                           "lead_preferred_hour_entries": len(sn["lead_preferred_hour"])}
    return out
