"""Independent Chip Model: tournament chip stacks -> expected prize money.

Malmuth-Harville: each remaining place is won by a remaining player with
probability proportional to stack. This is exactly a Plackett-Luce ranking with
weights = stacks, which the Monte Carlo version samples via the Gumbel-max trick.

Zero-stack rule: a player with stack 0 has already busted and gets equity 0.
Busted players occupy the bottom places, so the `m` live players compete only
for `payouts[:m]`; payouts for places beyond `m` are ignored (already awarded).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

MAX_EXACT_PLAYERS = 9


class ICMError(ValueError):
    pass


def _prepare(stacks, payouts) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    s = np.asarray(stacks, dtype=float)
    p = np.asarray(payouts, dtype=float)
    if s.ndim != 1 or s.size == 0:
        raise ICMError("stacks must be a non-empty 1-D sequence.")
    if p.ndim != 1:
        raise ICMError("payouts must be a 1-D sequence ordered by finishing place.")
    if np.any(s < 0) or not np.all(np.isfinite(s)):
        raise ICMError("stacks must be finite and non-negative; use 0 for busted players.")
    if np.any(p < 0) or not np.all(np.isfinite(p)):
        raise ICMError("payouts must be finite and non-negative.")
    live = np.flatnonzero(s > 0)
    if live.size == 0:
        raise ICMError("all stacks are 0: at least one live player is required.")
    return s, p[: live.size], live


def icm_equity(stacks, payouts) -> list[float]:
    """Exact Malmuth-Harville equity per player, same units as `payouts`.

    At most `MAX_EXACT_PLAYERS` live players (cost grows as 2^n); use
    `icm_equity_mc` beyond that.
    """
    s, p, live = _prepare(stacks, payouts)
    m = live.size
    if m > MAX_EXACT_PLAYERS:
        raise ICMError(f"{m} live players exceed exact limit {MAX_EXACT_PLAYERS}; "
                       "use icm_equity_mc.")
    w = s[live]
    full = (1 << m) - 1

    @lru_cache(maxsize=None)
    def expected(mask: int) -> tuple[float, ...]:
        # Expected prize of each player given the players in `mask` remain for
        # the next places (those outside `mask` already finished higher).
        place = m - mask.bit_count()
        out = [0.0] * m
        if place >= p.size:
            return tuple(out)
        members = [i for i in range(m) if mask >> i & 1]
        total = sum(w[i] for i in members)
        for i in members:
            pi = w[i] / total
            out[i] += pi * p[place]
            rest = expected(mask & ~(1 << i))
            for j in members:
                out[j] += pi * rest[j]
        return tuple(out)

    eq = np.zeros(s.size)
    eq[live] = expected(full)
    return eq.tolist()


def icm_equity_mc(stacks, payouts, n_samples: int, rng: np.random.Generator) -> list[float]:
    """Monte Carlo ICM equity for any player count (vectorised Gumbel-max).

    Pass a generator seeded identically across calls to get common random
    numbers, so differences between nearby stack vectors have low variance.
    """
    if n_samples <= 0:
        raise ICMError("n_samples must be positive.")
    s, p, live = _prepare(stacks, payouts)
    m = live.size
    k = p.size
    eq = np.zeros(s.size)
    if k == 0:
        return eq.tolist()
    keys = np.log(s[live]) + rng.gumbel(size=(n_samples, m))
    if k < m:
        top = np.argpartition(-keys, k - 1, axis=1)[:, :k]
    else:
        top = np.broadcast_to(np.arange(m), (n_samples, m))
    order = np.argsort(-np.take_along_axis(keys, top, axis=1), axis=1)
    ranked = np.take_along_axis(top, order, axis=1)
    won = np.bincount(ranked.ravel(), weights=np.tile(p, n_samples), minlength=m)
    eq[live] = won / n_samples
    return eq.tolist()
