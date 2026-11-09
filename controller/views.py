"""Read-only views over the controller's own store (never the simulator's logs).

* supervisor_view — the "one screen" (stakeholders/04): KPIs, what we want from you, what's being
  tested, what's winning, what changed today, caller IDs, incidents, what you pinned.
* why            — "why did workflow X change at T, who approved it, what happened next?"
* health         — the loop's own health for the on-call engineer.
"""
from __future__ import annotations

import json

from .store import Store


def fmt(m) -> str:
    if m is None:
        return "—"
    d, mod = divmod(int(m), 1440)
    return f"D{d} {mod // 60:02d}:{mod % 60:02d}"


def parse_when(s: str) -> int:
    s = s.strip()
    if s.lstrip("-").isdigit():
        return int(s)
    day, hm = s.split()
    h, m = hm.split(":")
    return int(day.lstrip("Dd")) * 1440 + int(h) * 60 + int(m)


def _aggs(store: Store):
    snap = store.load_snapshot()
    return (snap[2]["aggs"], snap[1]) if snap else ({}, None)


def _kpi(agg, days) -> dict:
    d = c = e = 0
    for day in days:
        k = agg.daily_kpis(day)
        d, c, e = d + k["dials"], c + k["connected"], e + k["engaged"]
    return {"dials": d, "pickup": c / d if d else None, "engagement": e / c if c else None}


def _pct(x):
    return "—" if x is None else f"{x:.1%}"


def workflows(store: Store) -> list[str]:
    return [r[0] for r in store.q("SELECT DISTINCT workflow_id FROM config_versions ORDER BY workflow_id")]


def supervisor_view(store: Store, wid: str) -> str:
    aggs, snap_min = _aggs(store)
    now = store.one("SELECT MAX(sim_minute) FROM decisions")[0] or 0
    today = now // 1440
    agg = aggs.get(wid)
    base = store.get(f"baseline:{wid}") or {}
    L = [f"## {wid} — supervisor view at {fmt(now)}", ""]
    if agg:
        t, y = _kpi(agg, [today]), _kpi(agg, [today - 1])
        live = _kpi(agg, [d for d in agg.days() if d >= 0])
        L += ["| | pickup | engagement | dials |", "|---|---|---|---|",
              f"| today so far | {_pct(t['pickup'])} | {_pct(t['engagement'])} | {t['dials']} |",
              f"| yesterday | {_pct(y['pickup'])} | {_pct(y['engagement'])} | {y['dials']} |",
              f"| since D0 | {_pct(live['pickup'])} | {_pct(live['engagement'])} | {live['dials']} |",
              f"| history (before D0) | {_pct(base.get('pickup'))} | {_pct(base.get('engagement'))} | "
              f"{int(base.get('dials_per_day', 0))}/day |", ""]
    pend = store.proposals(wid, ("pending", "approved", "submitting"))
    L.append("### What we want from you")
    if not pend:
        L.append("Nothing pending.")
    for p in sorted(pend, key=lambda p: -(p["body"].get("impact_score") or 0)):
        b = p["body"]
        L.append(f"- **{p['approval_id'] or p['proposal_id']}** ({p['status']}, impact {b.get('impact_score')}, "
                 f"{b.get('affected_leads')} leads): {b.get('change_summary')}")
    L += ["", "### What's being tested / what's winning"]
    arms = store.arms(wid)
    control = store.get(f"control:{wid}") or {}
    pins = store.pins(wid)
    for dim in ("welcome_message", "voice"):
        if dim in pins:
            L.append(f"- {dim}: **paused** — you set it at {fmt(pins[dim]['since_minute'])}; we won't change it")
            continue
        rows = sorted((k, v) for k, v in arms.items() if k[0] == dim)
        states = ", ".join(f"{o}{'' if seg == 'all' else '[' + seg + ']'}={r['state']}"
                           f"({(r.get('detail') or {}).get('lift', '')})" for (d, seg, o), r in rows) or "all exploring"
        L.append(f"- {dim} (control {control.get(dim)}): {states}")
    cur = store.one("SELECT config FROM config_versions WHERE workflow_id=? AND config IS NOT NULL ORDER BY version "
                    "DESC LIMIT 1", wid)
    if cur:
        cfg = json.loads(cur[0])
        a = cfg["allocations"]["default"]
        L.append(f"- live default mix: welcome {a.get('welcome_message')}, voice {a.get('voice')}, "
                 f"caller ID {a.get('caller_id')}; {len(cfg.get('cohorts') or [])} cohorts; prompt "
                 f"{cfg.get('prompt_version')}")
    L += ["", "### Caller IDs"]
    for did, r in store.dids(wid).items():
        ev = r.get("detail") or {}
        L.append(f"- {did}: {r['state']} since {fmt(r['since_minute'])} ({ev.get('reason')}"
                 f"{', ratio ' + str(ev.get('ratio')) if ev.get('ratio') else ''})")
    L += ["", "### What changed today"]
    rows = store.q("SELECT * FROM config_versions WHERE workflow_id=? AND sim_minute >= ? ORDER BY version", wid,
                   today * 1440)
    if not rows:
        L.append("No config changes today.")
    for r in rows:
        p = store.proposal(r["proposal_id"]) if r["proposal_id"] else None
        why = (p["body"].get("change_summary") if p else "") or ""
        L.append(f"- {fmt(r['sim_minute'])} v{r['version']} by {r['actor']}"
                 f"{' (' + r['approval_id'] + ')' if r['approval_id'] else ''}: {json.loads(r['changed_dims'] or '[]')}"
                 f" {why}")
    L += ["", "### Incidents"]
    incs = store.incidents(wid)
    if not incs:
        L.append("None.")
    for i in incs:
        d = i["detail"] or {}
        L.append(f"- #{i['id']} {i['kind']} {i['status']} (opened {fmt(i['opened_minute'])}, resolved "
                 f"{fmt(i['resolved_minute'])}): {d.get('summary') or (d.get('spike') or {}).get('flag_rate', '')}")
    return "\n".join(L)


def why(store: Store, wid: str, at: int) -> str:
    v = store.one("SELECT * FROM config_versions WHERE workflow_id=? AND sim_minute <= ? ORDER BY version DESC LIMIT 1",
                  wid, at)
    if v is None:
        return f"No config version of {wid} at or before {fmt(at)}."
    v = dict(v)
    L = [f"# Why did {wid} look the way it did at {fmt(at)}?", "",
         f"Active: **v{v['version']}**, set at {fmt(v['sim_minute'])} by **{v['actor']}**, changed "
         f"{json.loads(v['changed_dims'] or '[]')}"]
    if v["actor"] == "supervisor":
        L.append("This was a client supervisor edit (outside our governance path). Our response:")
        for r in store.q("SELECT * FROM decisions WHERE workflow_id=? AND kind='supervisor_edit' AND sim_minute>=? "
                         "ORDER BY id LIMIT 3", wid, v["sim_minute"]):
            L.append(f"- {fmt(r['sim_minute'])} {r['summary']}")
    p = store.proposal(v["proposal_id"]) if v["proposal_id"] else None
    if p:
        b = p["body"]
        L += ["", f"## The change ({p['path']}, purpose: {p['purpose']})",
              f"- proposal `{p['proposal_id']}` created {fmt(p['created_minute'])}"
              + (f", approval **{p['approval_id']}** decided {fmt(p['decided_minute'])}" if p["approval_id"] else
                 " — auto-applied within the workflow's signed auto-apply policy"),
              f"- applied {fmt(p['applied_minute'])} as v{p['applied_version']}",
              f"- summary: {b.get('change_summary')}",
              f"- impact score {b.get('impact_score')}, affected leads {b.get('affected_leads')}",
              f"- expected: {(b.get('dry_run') or b.get('evidence', {}).get('dry_run') or {}).get('expected_relative_change')}",
              "", "### Rationale", "```", str(b.get("rationale")), "```", "", "### Diff", "```",
              json.dumps(b.get("diff"), indent=1)[:3000], "```"]
        L += ["", "### Decisions that led to it"]
        prev = store.one("SELECT sim_minute FROM config_versions WHERE workflow_id=? AND version<? ORDER BY version DESC"
                         " LIMIT 1", wid, v["version"])
        since = prev[0] if prev else -10**9
        for r in store.q("SELECT * FROM decisions WHERE workflow_id=? AND sim_minute BETWEEN ? AND ? AND (kind LIKE "
                         "'arm_%' OR kind LIKE 'did_%' OR kind LIKE 'incident_%' OR proposal_id=?) ORDER BY id",
                         wid, since, v["sim_minute"], p["proposal_id"]):
            L.append(f"- {fmt(r['sim_minute'])} [{r['kind']}] {r['summary']}")
    L += ["", "## What happened next"]
    nxt = store.one("SELECT * FROM config_versions WHERE workflow_id=? AND version>? ORDER BY version LIMIT 1", wid,
                    v["version"])
    end = nxt["sim_minute"] if nxt else None
    aggs, _ = _aggs(store)
    agg = aggs.get(wid)
    if agg:
        d0 = v["sim_minute"] // 1440
        before, after = _kpi(agg, [d0 - 1]), _kpi(agg, [d0 + 1])
        L.append(f"- day before (D{d0 - 1}): pickup {_pct(before['pickup'])}, engagement {_pct(before['engagement'])}; "
                 f"day after (D{d0 + 1}): pickup {_pct(after['pickup'])}, engagement {_pct(after['engagement'])}")
    for r in store.q("SELECT * FROM decisions WHERE workflow_id=? AND sim_minute > ? AND sim_minute <= ? AND kind NOT "
                     "IN ('reconcile') ORDER BY id LIMIT 15", wid, v["sim_minute"], end if end is not None else 10**9):
        L.append(f"- {fmt(r['sim_minute'])} [{r['kind']}] {r['summary']}")
    if nxt:
        L.append(f"- superseded by v{nxt['version']} at {fmt(nxt['sim_minute'])} ({nxt['actor']})")
    return "\n".join(L)


def health(store: Store) -> str:
    L = ["# Controller health", ""]
    rs = store.get("run_stats") or {}
    for name in ("ingest_events_per_s", "ingest_lag_chunks", "decisions_per_day", "credits_remaining", "snapshot_s",
                 "peak_rss_mb"):
        r = store.one("SELECT AVG(value), MAX(value), COUNT(*), MAX(sim_minute) FROM metrics WHERE name=?", name)
        last = store.one("SELECT value FROM metrics WHERE name=? ORDER BY rowid DESC LIMIT 1", name)
        if r and r[2]:
            L.append(f"- {name}: last {last[0]:.1f}, avg {r[0]:.1f}, max {r[1]:.1f} (n={r[2]})")
    if rs:
        L.append(f"- run: {json.dumps({k: (round(v, 1) if isinstance(v, float) else v) for k, v in rs.items()})}")
    L += ["", "## Open alerts"]
    for a in store.q("SELECT * FROM alerts WHERE resolved_minute IS NULL ORDER BY severity DESC, id"):
        L.append(f"- [{a['severity'].upper()}] {fmt(a['sim_minute'])} {a['workflow_id'] or ''} {a['code']}: "
                 f"{a['message']} → {a['runbook']}")
    L += ["", "## Proposal outcomes"]
    for r in store.q("SELECT path, purpose, status, COUNT(*) n FROM proposals GROUP BY 1,2,3 ORDER BY 1,2,3"):
        L.append(f"- {r['path']}/{r['purpose']}: {r['status']} × {r['n']}")
    return "\n".join(L)
