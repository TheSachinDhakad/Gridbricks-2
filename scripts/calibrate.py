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


if __name__ == "__main__":
    main()
