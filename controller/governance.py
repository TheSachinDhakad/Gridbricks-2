"""Governance client policy: when we may ask, how often, and how a proposal moves through its life.

Proposal lifecycle (our side; the simulator's states are a subset):

    planned ──► submitting ──► pending ──► approved ──► applied
                    │             │            │
                    │             ├─► rejected ├─► lapsed   (not applied inside apply_window)
                    │             └─► expired  └─► stale    (base_version moved: supervisor edit)
                    └─► not_sent   (crash between intent and POST; re-planned from fresh data)
    auto:  planned ──► applied | refused (403)

Expired, rejected, lapsed and stale proposals are never resubmitted as-is: the planner rebuilds the
desired config from current data and current base_version at the next allowed slot (stakeholders/05).

Request budget per workflow per rolling 24h (max_requests_per_24h = M):
    routine     ≤ min(max(1, M−2), tenant preference), and only while ≥1 slot stays free
    protective  (roll back / stop a harmful arm) any time in approver hours, leaving 1 slot free
    incident    (hallucination fix) any time, may use the last slot
"""
from __future__ import annotations

from dataclasses import dataclass

from . import settings as S

INFLIGHT = ("planned", "submitting", "pending", "approved")


@dataclass
class Policy:
    wid: str
    tenant: str
    auto_enabled: bool
    allowed_dims: tuple
    max_shift: float
    approver_hours: tuple
    latency: tuple
    ttl_hours: float
    apply_window_hours: float
    max_requests: int
    min_validation: float
    mid_flight: str
    earliest_submit_hour: int
    max_routine: int

    @classmethod
    def from_meta(cls, meta: dict) -> "Policy":
        g = meta["governance"]
        aa = g.get("auto_apply") or {}
        prefs = S.TENANT_PREFS.get(meta["tenant_id"], {})
        M = int(g.get("max_requests_per_24h", 4))
        lo, hi = g.get("approver_hours", [10, 19])
        return cls(wid=meta["workflow_id"], tenant=meta["tenant_id"], auto_enabled=bool(aa.get("enabled")),
                   allowed_dims=tuple(aa.get("allowed_dims") or ()), max_shift=float(aa.get("max_shift") or 0),
                   approver_hours=(lo, hi), latency=tuple(g.get("approver_latency_minutes", [20, 240])),
                   ttl_hours=float(g.get("proposal_ttl_hours", 24)),
                   apply_window_hours=float(g.get("apply_window_hours", 2)), max_requests=M,
                   min_validation=float(g.get("min_validation_pass_rate", 0.97)),
                   mid_flight=meta.get("mid_flight", "allowed"),
                   earliest_submit_hour=max(lo, int(prefs.get("earliest_submit_hour", lo))),
                   max_routine=min(max(1, M - 2), int(prefs.get("max_routine_per_day", 99))))

    def auto_allows(self, dims) -> bool:
        return self.auto_enabled and bool(dims) and all(d in self.allowed_dims for d in dims)

    # ------------------------------------------------------------------ timing
    def in_approver_hours(self, minute: int) -> bool:
        h = (minute % 1440) / 60
        return self.approver_hours[0] <= h < self.approver_hours[1]

    def routine_window(self, minute: int) -> bool:
        """Submit routine requests only when the approver can decide them today."""
        mod = minute % 1440
        start = self.earliest_submit_hour * 60
        end = self.approver_hours[1] * 60 - self.latency[1]
        if end <= start:          # max latency longer than the working day: send first thing
            end = start + 60
        return start <= mod < end


def requests_24h(store, wid: str, now: int, purposes: tuple | None = None) -> int:
    sql = ("SELECT COUNT(*) FROM proposals WHERE workflow_id=? AND path='approval' AND submitted_minute IS NOT NULL "
           "AND submitted_minute > ? AND status NOT IN ('not_sent')")
    args = [wid, now - 1440]
    if purposes:
        sql += f" AND purpose IN ({','.join('?' * len(purposes))})"
        args += list(purposes)
    return store.one(sql, *args)[0]


def may_submit(pol: Policy, store, now: int, purpose: str) -> tuple[bool, str]:
    used = requests_24h(store, pol.wid, now)
    if purpose == "incident":
        return (used + 1 <= pol.max_requests, f"{used}/{pol.max_requests} requests used in 24h")
    reserve = 1 if pol.max_requests >= 2 else 0
    if used + 1 > pol.max_requests - reserve:
        return False, f"{used}/{pol.max_requests} used; last slot reserved for incidents"
    if purpose == "protective":
        return (pol.in_approver_hours(now), "outside approver hours")
    routine_used = requests_24h(store, pol.wid, now, ("routine",))
    if routine_used >= pol.max_routine:
        return False, f"routine budget {routine_used}/{pol.max_routine} used"
    if not pol.routine_window(now):
        return False, "outside routine submission window"
    return True, "ok"


def inflight(store, wid: str, purposes: tuple | None = None) -> list[dict]:
    rows = store.proposals(wid, INFLIGHT)
    return [r for r in rows if purposes is None or r["purpose"] in purposes]
