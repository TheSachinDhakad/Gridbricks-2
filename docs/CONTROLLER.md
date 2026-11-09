# Controller — operator & developer guide

For the engineer who gets paged while the author is on leave. The *why* behind every design choice
is in `SUBMISSION.md`; this file is the *how*.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh http://127.0.0.1:8700                          # contract: runs until the scenario finishes
scripts/run_scenario.sh scenarios/public_01_dev.yaml    # baseline + sim + controller + grade, one command
scripts/crash_test.sh scenarios/public_02_incidents.yaml 4   # SIGKILL ×4 mid-run, restart, verify, grade
python -m pytest -q tests                               # unit + in-process end-to-end crash test
python scripts/calibrate.py                             # A/A Monte-Carlo behind the statistical thresholds
```

No Docker, no services: Python ≥3.10, `numpy` + `httpx` (already in requirements) and stdlib `sqlite3`.
State is one SQLite file per scenario in `state/` (`STATE_DIR` to override). Restarting `./run.sh`
against the same simulator resumes; pointing it at a different/new world archives the old file
(`*.db.stale-<ts>`) and starts fresh.

## Ask it questions

```bash
python -m controller view   --workflow nw_renewal            # the supervisor's one screen
python -m controller why    --workflow ks_cancel --at "D3 14:00"   # why did X change, who approved, what next
python -m controller audit  --workflow ks_cancel --kind 'incident%'  # raw decision log (SQL LIKE on kind)
python -m controller health                                  # loop health + open alerts + proposal outcomes
sqlite3 state/<scenario>.db 'select * from proposals'        # everything is plain SQL
```

## Map of the code

| file | responsibility |
|---|---|
| `controller/controller.py` | the loop: bootstrap → ingest → decide → act, recovery, incidents, proposal content |
| `controller/aggregates.py` | NDJSON → per-day numpy cubes (cell × arm, hour × cell, hour × DID, hour × prompt) |
| `controller/features.py` | lead feature vocabulary, cells, the shared `Cohort` object, first-match semantics |
| `controller/experiments.py` | welcome/voice arm states, winner / harm / futility / decay rules, allocations |
| `controller/callerid.py` | caller-ID health states and the rotation target |
| `controller/schedule.py` | call-time weights from history, cohort partition builder |
| `controller/incidents.py` | hallucination spike test, proven-prompt lookup |
| `controller/governance.py` | policy object, request budget, submission windows, lifecycle doc |
| `controller/configtools.py` | contract mirrors: dist resolution, changed dims, TV shift, stepping |
| `controller/store.py` | SQLite schema: decisions, proposals, versions, arms, dids, incidents, pins, metrics, alerts, snapshots |
| `controller/views.py` | supervisor view, why-query, health |
| `controller/settings.py` | **every** threshold, with its reason |

## The loop in one paragraph

Every tick (15 sim-minutes while anyone is dialling or approving, one jump overnight) the controller
(1) polls in-flight approvals and applies approved ones immediately; (2) per workflow, checks caller-ID
health and hallucination flags, advances experiment arm states hourly, and recomputes the config it
*wants* (`compose`), which is a pure function of stored state; (3) routes the difference: dims the
policy lets us auto-apply go out one `max_shift` step per tick, the rest are bundled into one approval
request when the budget and submission window allow; (4) advances the simulator and ingests the new
chunks. Each side effect is written to the store *before* the HTTP call.

## Alerts and what to do

| code | severity | meaning | action |
|---|---|---|---|
| `hallucination` | page | flag rate on the live prompt spiked; a fix is being validated | usually none — watch `view`; it escalates if unfixed |
| `hallucination_unfixed` | page | >2h without an applied fix | check the approver queue (`view`); consider a manual rollback |
| `hallucination_no_fix` | page | no prompt passed validation / credits exhausted | human picks a prompt or pauses the workflow |
| `approved_not_applied` | page | an approval sat >60 min unapplied (apply window is 2h) | check `state/<scenario>.log` for apply errors |
| `credits_low` | page | <10 credits with an open incident | top up, or roll back manually |
| `did_bad:<D>` | ticket | a caller ID was rotated out | check carrier spam status; re-add manually after remediation |
| `decay:<dim>:<opt>` | ticket | a promoted variant stopped winning and was rolled back | none |
| `guardrail_breach` | ticket | guardrail KPI over 2 days dropped more than allowed | `why` on the last change; usually call-time composition |
| `proposal_rejected/expired/lapsed` | ticket | an approval did not go through | none — re-planned automatically |
| `supervisor_edit` | ticket | a supervisor changed config; those dims are now pinned | none |

Nothing else pages. Everything is also in `alerts` (SQL) and `health`.

## Recovery model (what happens on `kill -9`)

* Aggregates: snapshot (pickled cubes + vocab + last chunk number) every 6 sim-hours, in one SQLite
  transaction. On restart: load the snapshot and replay chunks newer than its watermark. Events are
  only counted via this path, so nothing is double-counted.
* Control-plane events (`config_changed`) are handled once, guarded by `kv.ctl_event_id`.
* Proposals are inserted as `submitting` before the POST/PUT. On restart, `_reconcile` asks the
  simulator: found → adopt its approval id/version; not found → `not_sent` and re-plan from fresh data.
* Approved-but-unapplied approvals are found by polling and applied (if still in the apply window).
* Learnt state (arm states, DID states, pins, schedule, baselines) is in SQLite rows, never in memory only.

## Extending it

* New lever: add its target to `Controller.compose`, its evidence to `_rationale`/`_dry_run`; the
  governance routing (auto vs. approval, stepping, budgeting) is generic over changed dims.
* New threshold: put it in `settings.py` with a reason, and add a case to `scripts/calibrate.py` if it's
  a statistical rule.
* New tenant courtesy limit: `settings.TENANT_PREFS`.
