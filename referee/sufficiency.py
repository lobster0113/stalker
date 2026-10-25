"""Cell-level data sufficiency (referee/DATA_SUFFICIENCY.md §1): S1 precision, S4 reproducibility, S5 saturation.

A *cell* is a list of decisions; each decision is the AI's action-probability vector plus the
tournament it came from. Decisions from one tournament are correlated, so every variance here
is a tournament-cluster bootstrap (`referee.stats.bootstrap_ci`), never a raw-n formula.
`lessonable = S1 and S4 and S5`; S2/S3/S6 and dataset-level D1~D5 are not computed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist
from typing import Sequence

import numpy as np

from referee.stats import bootstrap_ci

S1_HALF_WIDTH = 0.05
S4_TOL = 0.05
S5_TOL = 0.02
S5_FRACTION = 0.8
MAJOR_MIN = 0.05  # actions averaging below this are not "major" and are not gated by S1
_EPS = 1e-9  # a difference of exactly the tolerance passes despite float error


@dataclass(frozen=True)
class Cell:
    probs: np.ndarray  # (n, n_actions), rows sum to 1
    tournaments: np.ndarray  # (n,) tournament id per decision


def make_cell(probs: Sequence[Sequence[float]], tournament_ids: Sequence[object]) -> Cell:
    p = np.asarray(probs, dtype=float)
    if p.ndim != 2 or p.shape[0] == 0:
        raise ValueError(f"probs must be a non-empty (n, n_actions) array, got shape {p.shape}.")
    if len(tournament_ids) != len(p):
        raise ValueError(f"{len(tournament_ids)} tournament ids for {len(p)} decisions; pass one per decision.")
    if not np.all(np.isfinite(p)) or np.any(p < 0) or not np.allclose(p.sum(axis=1), 1.0, atol=1e-6):
        raise ValueError("each probability vector must be finite, non-negative and sum to 1 (D5).")
    return Cell(p, np.asarray([str(t) for t in tournament_ids]))


@dataclass(frozen=True)
class ActionPrecision:
    action: int
    mean: float
    half_width: float
    ess: float


@dataclass(frozen=True)
class S1Result:
    passed: bool
    actions: tuple[ActionPrecision, ...]


def rule_of_three(n_tournaments: int) -> float:
    """95% upper bound 3/n on a rate never observed in n independent tournaments."""
    return 3 / n_tournaments


def s1_precision(cell: Cell, *, half_width: float = S1_HALF_WIDTH, major_min: float = MAJOR_MIN,
                 n_boot: int = 2000, rng: np.random.Generator) -> S1Result:
    """Every major action's 95% half-width, max(cluster-bootstrap, rule of three 3/n_tournaments), must be <= `half_width`.

    The rule-of-three floor applies always, not only at zero variance: a bootstrap over n tournaments cannot
    see a deviation rarer than about 1/n, so a near-deterministic action escapes it just like a deterministic
    one (an only-at-zero floor would let one stray 0.999 decision skip the bound). With n >= ceil(3 / half_width)
    tournaments the floor is within the criterion and only the bootstrap decides.
    ESS is the n whose normal-approximation half-width equals the reported one; with zero bootstrap variance
    that is the n of the rule of three, i.e. the number of tournaments.
    """
    n_t = len(np.unique(cell.tournaments))
    if n_t < 2:
        return S1Result(False, ())  # one tournament: variance is not estimable, so not sufficient
    z = NormalDist().inv_cdf(0.975)
    floor = rule_of_three(n_t)
    out = []
    for a in np.flatnonzero(cell.probs.mean(axis=0) >= major_min):
        ci = bootstrap_ci(cell.probs[:, a], cell.tournaments, n_boot=n_boot, rng=rng)
        boot_hw = (ci.hi - ci.lo) / 2
        hw = max(boot_hw, floor)
        ess = ci.mean * (1 - ci.mean) / (hw / z) ** 2 if boot_hw > 0 else float(n_t)
        out.append(ActionPrecision(int(a), ci.mean, hw, ess))
    return S1Result(bool(out) and all(r.half_width <= half_width + _EPS for r in out), tuple(out))


def _agree(a: Cell, b: Cell, tol: float) -> bool:
    ma, mb = a.probs.mean(axis=0), b.probs.mean(axis=0)
    if ma.shape != mb.shape:
        raise ValueError(f"cells have {ma.shape[0]} vs {mb.shape[0]} actions; compare cells of one action set.")
    return int(ma.argmax()) == int(mb.argmax()) and bool(np.all(np.abs(ma - mb) <= tol + _EPS))


def s4_reproducible(a: Cell, b: Cell, *, tol: float = S4_TOL) -> bool:
    """Two independently seeded datasets give the same main action and frequencies within `tol`."""
    return _agree(a, b, tol)


def s5_saturated(cell: Cell, *, fraction: float = S5_FRACTION, tol: float = S5_TOL,
                 rng: np.random.Generator) -> bool:
    """A random `fraction` of tournaments agrees with the full cell (same main action, within `tol`)."""
    ids = np.unique(cell.tournaments)
    k = int(len(ids) * fraction)  # floor: never keep more than `fraction`, which would loosen the criterion
    if k < 1 or k >= len(ids):
        return False  # the subset equals the full cell, so saturation cannot be judged; collect more tournaments
    keep = rng.choice(ids, size=k, replace=False)
    mask = np.isin(cell.tournaments, keep)
    return _agree(Cell(cell.probs[mask], cell.tournaments[mask]), cell, tol)


@dataclass(frozen=True)
class Verdict:
    s1: S1Result
    s4: bool
    s5: bool

    @property
    def lessonable(self) -> bool:
        return self.s1.passed and self.s4 and self.s5


def judge_cell(a: Cell, b: Cell, *, seed: int = 0) -> Verdict:
    """S1 and S5 on dataset `a`, S4 between `a` and the independently seeded `b`."""
    rng = np.random.default_rng(seed)
    return Verdict(s1_precision(a, rng=rng), s4_reproducible(a, b), s5_saturated(a, rng=rng))
