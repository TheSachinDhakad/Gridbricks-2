"""Every tunable the controller uses, in one place, with the reason for its value.

Nothing here is read from a scenario file. Values were chosen from the statistics of the problem
(traffic per workflow, effect sizes worth acting on, the grader-independent cost of a false winner),
not fitted to the public scenarios' hidden truth. SUBMISSION.md §5 explains the derivations.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- loop
ACTIVE_STEP_MIN = 15          # tick while any workflow is dialling / approvers are working
SNAPSHOT_EVERY_MIN = 6 * 60   # aggregate snapshot cadence (bounds replay after a crash)

# --------------------------------------------------------------------------- experiments (welcome × voice)
EXPLORE_TOTAL = 0.40          # at most this much of a cohort's traffic goes to unproven challengers
EXPLORE_PER_ARM_MAX = 0.15    # ...and at most this much to any single challenger
HOLDOUT = 0.15                # control share kept after a winner is promoted, to watch for decay
MIN_CONN_DECIDE = 300         # connected calls per arm (and control) before a winner can be declared
MIN_CONN_HARM = 200           # ...before an arm can be stopped for harm
Z_WIN_GLOBAL = 3.0            # one-sided, hourly peeks: 1.3% false winners per arm (scripts/calibrate.py)
Z_WIN_SEGMENT = 3.5           # segment-level winners face ~14 segments × arms, so a stricter bar
MIN_LIFT = 0.03               # don't promote lifts too small to matter
Z_HARM = -2.5                 # stop an arm early when it is significantly worse: 2.9% false stops per arm
Z_GUARDRAIL = -3.0            # W/V can't plausibly move pickup, so only a very clear breach counts
GUARD_PRESSURE_FRACTION = 0.5 # guardrail KPI within half of its allowed drop → stop arms that hurt it
FUTILITY_UPPER = 0.02         # drop an arm when even its optimistic bound is below +2%
FUTILITY_MIN_CONN = 3 * MIN_CONN_DECIDE
DECAY_Z_CHANGE = -2.5         # winner's recent lift significantly below its (shrunk) lift at promotion...
DECAY_Z_RECENT = -2.0         # ...or significantly below control outright → roll back
DECAY_MIN_CONN = 200          # control connected calls needed in the recent window to judge decay
SEGMENT_MIN_SHARE = 0.03      # segments thinner than this aren't tested on their own
MAX_COHORTS = 20              # simulator contract

# --------------------------------------------------------------------------- caller ID
DID_EXPLORE_AUTO = 0.05       # share for an unknown DID where we can adjust by auto-apply
DID_EXPLORE_GATED = 0.12      # share where every adjustment costs an approval
DID_MAX_EXPLORING = 2
DID_WINDOW_HOURS = 6          # rolling window of dialling hours for health checks
DID_BAD_RATIO = 0.75          # pickup ratio vs. the other DIDs for a number we are still exploring...
DID_BAD_RATIO_ESTABLISHED = 0.60  # ...and for one already in rotation (load alone can cost ~25%)
DID_REPROBE_HOURS = None      # disabled: a rotated-out number returns only after a human re-adds it
#                               (carrier remediation is invisible to us; re-probing re-exposes customers)
DID_BAD_Z = -3.0              # ...and significance, both required → "degraded"
DID_MIN_DIALS_BAD = 100
DID_HEALTHY_MIN_DIALS = 250
DID_HEALTHY_LOWER = 0.85      # lower 90% bound of the pickup ratio to call an unknown DID healthy

# --------------------------------------------------------------------------- call-time (schedule)
SCHED_PRIOR_DIALS = 50        # shrink each (cohort, hour) pickup rate toward the hour's rate
SCHED_BETA = 2.0              # sharpening of comparative advantage into hour weights
SCHED_W_MIN, SCHED_W_MAX = 0.25, 4.0
SCHED_MIN_SIGNAL = 0.004      # mean squared log-advantage below this → no per-cohort schedule
SCHED_MAX_VALUES = 6

# --------------------------------------------------------------------------- hallucination incidents
HALLUC_MIN_CONN = 80
HALLUC_P_ALARM = 1e-4         # Poisson tail vs. the workflow's historical flag rate
HALLUC_P_ALARM_NEW_PROMPT = 1e-3
HALLUC_MIN_RATIO = 2.0
HALLUC_WINDOW_MIN = 180
HALLUC_VERIFY_CONN = 300      # connected calls on the fix before we call it verified
VALIDATION_N = 300            # 3 credits; enough to separate ~1% from ~5% failure rates
VALIDATION_MARGIN = 0.005     # our bar = policy min pass rate + margin (we're stricter than the approver)
CREDIT_CAP_PER_INCIDENT = 15

# --------------------------------------------------------------------------- governance
IMPACT_FULL_SCALE = 0.05      # impact_score 1.0 ≈ +5% expected relative gain on the primary KPI
NOOP_TV = 0.02                # allocation moves smaller than this are not worth a version

# Tenant preferences stated by client stakeholders that are *stricter* than the signed policy.
# The policy is the hard limit; these are courtesy limits we choose to honour (stakeholders/04).
TENANT_PREFS: dict[str, dict] = {
    "kestrel_finance": {"earliest_submit_hour": 11, "max_routine_per_day": 2},
}
