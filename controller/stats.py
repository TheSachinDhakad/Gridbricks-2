"""Small, deterministic statistical tests. No randomness anywhere in winner selection."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Ratio:
    """Relative comparison of two binomial rates via the log ratio (delta method)."""
    s1: int
    n1: int
    s0: int
    n0: int
    log_ratio: float
    se: float

    @property
    def ratio(self) -> float:
        return math.exp(self.log_ratio)

    @property
    def lift(self) -> float:
        return self.ratio - 1.0

    @property
    def z(self) -> float:
        return self.log_ratio / self.se if self.se > 0 else 0.0

    def bound(self, z: float) -> float:
        """Ratio at log_ratio + z·se (z<0 → lower bound)."""
        return math.exp(self.log_ratio + z * self.se)

    @property
    def p1(self) -> float:
        return self.s1 / self.n1 if self.n1 else float("nan")

    @property
    def p0(self) -> float:
        return self.s0 / self.n0 if self.n0 else float("nan")

    def brief(self) -> dict:
        return {"rate": round(self.p1, 4), "n": self.n1, "ctrl_rate": round(self.p0, 4), "ctrl_n": self.n0,
                "lift": round(self.lift, 4), "lo90": round(self.bound(-1.645) - 1, 4),
                "hi90": round(self.bound(1.645) - 1, 4), "z": round(self.z, 2)}


def ratio_test(s1, n1, s0, n0) -> Ratio:
    """log(p1/p0) with a +0.5 continuity correction so empty cells don't explode."""
    p1 = (s1 + 0.5) / (n1 + 1.0)
    p0 = (s0 + 0.5) / (n0 + 1.0)
    se = math.sqrt(max((1 - p1) / ((n1 + 1.0) * p1), 0) + max((1 - p0) / ((n0 + 1.0) * p0), 0))
    return Ratio(int(s1), int(n1), int(s0), int(n0), math.log(p1 / p0), se)


def diff_z(s1, n1, s0, n0) -> tuple[float, float]:
    """Absolute difference p1 - p0 and its z (unpooled)."""
    if n1 == 0 or n0 == 0:
        return 0.0, 0.0
    p1, p0 = s1 / n1, s0 / n0
    se = math.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0) or 1e-9
    return p1 - p0, (p1 - p0) / se


def poisson_sf(k: int, lam: float) -> float:
    """P(X >= k) for X ~ Poisson(lam)."""
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    if lam > 500:  # normal approximation with continuity correction
        return 0.5 * math.erfc((k - 0.5 - lam) / math.sqrt(2 * lam))
    # sum the lower tail in log space; k is small (tens to hundreds) here
    term = math.exp(-lam)
    cdf = term
    for i in range(1, k):
        term *= lam / i
        cdf += term
        if term < 1e-300 and i > lam:
            break
    return max(0.0, 1.0 - cdf)


def z_change(a: Ratio, b: Ratio) -> float:
    """z of the difference between two log ratios (independent windows)."""
    se = math.sqrt(a.se ** 2 + b.se ** 2)
    return (a.log_ratio - b.log_ratio) / se if se > 0 else 0.0
