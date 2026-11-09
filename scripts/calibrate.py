"""Monte-Carlo calibration of the winner / harm / decay rules under the controller's real peeking schedule.

Not tied to any scenario's hidden truth: it simulates a challenger arm against control at the traffic
levels of a typical workflow and reports, for each candidate rule,
  * false-winner rate  (true lift 0, P(declared winner within the horizon))
  * false-harm rate    (true lift 0, P(stopped for harm))
  * power / median time to a win for true lifts of +8%, +12%, +15%

    python scripts/calibrate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from controller.stats import ratio_test  # noqa: E402

RNG = np.random.default_rng(7)
HOURS_PER_DAY, DAYS = 12, 8
CONN_PER_HOUR = 90          # connected calls/hour on a dev-sized workflow (~1000/day)
SHARE_ARM, SHARE_CTRL = 0.13, 0.60
P0 = 0.52


def simulate(lift: float, z_win: float, min_n: int, z_harm: float, min_harm: int, look_every_h: int, sims=4000):
    wins, harms, t_win = 0, 0, []
    p1 = min(P0 * (1 + lift), 0.95)
    T = HOURS_PER_DAY * DAYS
    na = RNG.poisson(CONN_PER_HOUR * SHARE_ARM, size=(sims, T)).cumsum(1)
    nc = RNG.poisson(CONN_PER_HOUR * SHARE_CTRL, size=(sims, T)).cumsum(1)
    ea = RNG.binomial(np.diff(na, prepend=0, axis=1), p1).cumsum(1)
    ec = RNG.binomial(np.diff(nc, prepend=0, axis=1), P0).cumsum(1)
    for s in range(sims):
        for t in range(look_every_h - 1, T, look_every_h):
            r = ratio_test(ea[s, t], na[s, t], ec[s, t], nc[s, t])
            if min(r.n1, r.n0) >= min_harm and r.z <= z_harm:
                harms += 1
                break
            if min(r.n1, r.n0) >= min_n and r.z >= z_win and r.lift >= 0.03:
                wins += 1
                t_win.append((t + 1) / HOURS_PER_DAY)
                break
    return wins / sims, harms / sims, (float(np.median(t_win)) if t_win else None)


def simulate_decay(holdout: float, true_path, z_recent=-1.645, sims=1500, days=6):
    """Winner on (1-holdout) vs control on holdout; daily engagement multiplier follows `true_path(day)`.
    Hourly checks on the last-2-days window; returns P(rollback) and median day of rollback."""
    from controller.stats import ratio_test as rt
    T = HOURS_PER_DAY * days
    rolled, when = 0, []
    for _ in range(sims):
        nw = RNG.poisson(CONN_PER_HOUR * (1 - holdout), T)
        nc = RNG.poisson(CONN_PER_HOUR * holdout, T)
        mult = np.array([true_path(t / HOURS_PER_DAY) for t in range(T)])
        ew = RNG.binomial(nw, np.minimum(P0 * mult, 0.95))
        ec = RNG.binomial(nc, P0)
        for t in range(HOURS_PER_DAY, T):
            lo = (t // HOURS_PER_DAY - 1) * HOURS_PER_DAY
            r = rt(ew[lo:t + 1].sum(), nw[lo:t + 1].sum(), ec[lo:t + 1].sum(), nc[lo:t + 1].sum())
            if min(r.n0, r.n1) >= 200 and r.z <= z_recent:
                rolled += 1
                when.append(t / HOURS_PER_DAY)
                break
    return rolled / sims, (float(np.median(when)) if when else None)


def main():
    rules = [("z_win 2.5 / harm -2.0 / hourly (v0)", 2.5, 250, -2.0, 120, 1),
             ("z_win 3.0 / harm -2.5 / hourly", 3.0, 300, -2.5, 200, 1),
             ("z_win 2.5 / harm -2.5 / every 6h", 2.5, 300, -2.5, 200, 6),
             ("z_win 2.8 / harm -2.5 / every 3h", 2.8, 300, -2.5, 200, 3)]
    print(f"{CONN_PER_HOUR} connected/h, arm share {SHARE_ARM}, control {SHARE_CTRL}, {DAYS} days, base {P0}")
    print(f"{'rule':<40} {'false win':>9} {'false harm':>10} | power(+8%, +12%, +15%) and median days to win")
    for name, zw, mn, zh, mh, every in rules:
        fw, fh, _ = simulate(0.0, zw, mn, zh, mh, every)
        res = [simulate(l, zw, mn, zh, mh, every, sims=1500) for l in (0.08, 0.12, 0.15)]
        pw = ", ".join(f"{w:.0%}@{t if t is None else round(t, 1)}d" for w, _, t in res)
        print(f"{name:<40} {fw:>9.1%} {fh:>10.1%} | {pw}")
    print("\nDecay rollback (recent 2-day window, z <= -1.645, hourly checks, 6 days after promotion)")
    stable = lambda d: 1.09                                         # a real +9% winner that keeps working
    decays = lambda d: 1.15 if d < 1 else max(0.90, 1.15 - 0.125 * (d - 1))  # +15% → -10% over days 1..3
    for h in (0.15, 0.20, 0.25):
        fr, _ = simulate_decay(h, stable)
        dr, dd = simulate_decay(h, decays)
        print(f"holdout {h:.2f}: false rollback of a +9% winner {fr:5.1%} | decaying winner rolled back "
              f"{dr:5.1%}, median day {dd:.1f} (it crosses below control at day 2.2)")


if __name__ == "__main__":
    main()
