"""Lead feature space and the one shared cohort object.

Every lead maps to a *cell*: one code per feature (lang × city_tier × age_band × value_band). All
aggregates are kept per cell, so any cohort — an AND across features of OR-lists of values, exactly
the simulator's `where` semantics — is a boolean mask over cells. Detection, experiments, the
supervisor view and the config we send all use `Cohort` objects resolved through this module, so
there is exactly one definition of "seniors in Tamil" (stakeholders/05).

Feature *values* are learnt from `lead` events (we never read the scenario), so the vocabulary is
dynamic and persisted with the aggregates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

FEATURES = ("lang", "city_tier", "age_band", "value_band")
CAP = {"lang": 8, "city_tier": 4, "age_band": 6, "value_band": 4}
_STRIDE = {}
_s = 1
for _f in reversed(FEATURES):
    _STRIDE[_f] = _s
    _s *= CAP[_f]
NCELL = _s  # 768


class Vocab:
    """value <-> code per feature. The last code of a full feature is an overflow bucket."""

    def __init__(self, values: dict[str, list[str]] | None = None):
        self.values: dict[str, list[str]] = {f: list((values or {}).get(f, [])) for f in FEATURES}
        self.index = {f: {v: i for i, v in enumerate(vs)} for f, vs in self.values.items()}
        self._codes: dict[str, np.ndarray] | None = None

    def code(self, f: str, v: str) -> int:
        i = self.index[f].get(v)
        if i is None:
            if len(self.values[f]) < CAP[f]:
                i = len(self.values[f])
                self.values[f].append(v)
                self.index[f][v] = i
            else:
                i = CAP[f] - 1
        return i

    def cell(self, feats: dict) -> int:
        c = 0
        for f in FEATURES:
            c += self.code(f, str(feats.get(f))) * _STRIDE[f]
        return c

    def cell_codes(self) -> dict[str, np.ndarray]:
        """feature -> value code of every cell (independent of the vocabulary contents)."""
        if self._codes is None:
            idx = np.arange(NCELL)
            self._codes = {f: (idx // _STRIDE[f]) % CAP[f] for f in FEATURES}
        return self._codes

    def mask(self, where: dict) -> np.ndarray:
        m = np.ones(NCELL, dtype=bool)
        codes = self.cell_codes()
        for f, vals in (where or {}).items():
            ok = [self.index[f][v] for v in vals if v in self.index[f]]
            m &= np.isin(codes[f], ok)
        return m

    def to_state(self) -> dict:
        return {f: list(v) for f, v in self.values.items()}


@dataclass(frozen=True)
class Cohort:
    """The shared cohort object. `where` uses the simulator's semantics (AND across, OR within)."""
    id: str
    where: dict = field(default_factory=dict)
    label: str = ""

    def to_config(self) -> dict:
        return {"id": self.id, "where": {k: list(v) for k, v in self.where.items()}}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_") or "x"


def cohort_index(cohorts: list[Cohort] | list[dict], vocab: Vocab) -> np.ndarray:
    """cell -> cohort position (0 = default, i+1 = cohorts[i]); first match wins, as in the simulator."""
    out = np.zeros(NCELL, dtype=np.int16)
    free = np.ones(NCELL, dtype=bool)
    for i, c in enumerate(cohorts):
        where = c.where if isinstance(c, Cohort) else c.get("where", {})
        m = free & vocab.mask(where)
        out[m] = i + 1
        free &= ~m
    return out


def segments(vocab: Vocab, cell_weight: np.ndarray, min_share: float) -> list[tuple[str, str, np.ndarray]]:
    """Single-feature segments (feature, value, cell mask) carrying at least `min_share` of the weight."""
    tot = float(cell_weight.sum()) or 1.0
    codes = vocab.cell_codes()
    out = []
    for f in FEATURES:
        for v, i in vocab.index[f].items():
            m = codes[f] == i
            if cell_weight[m].sum() / tot >= min_share:
                out.append((f, v, m))
    return out
