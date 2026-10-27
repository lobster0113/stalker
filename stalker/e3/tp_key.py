"""E3-1: TP keys for N-handed play — the policy table is keyed by the TP vector, not the history (#196).

Design note #192 §3. A decision's key is

    pos | street | n_opp | raise level | initiative | hand.equity step | pot-odds step | SPR step

- n_opp: opponents still in the hand, capped at 3 ("3+").
- raise level: raises on this street (preflop the big blind does not count), capped at 3.
- initiative: who made the last bet or raise of the previous street (0 nobody / 1 me / 2 someone
  else); preflop 0.
- hand.equity: the chance to beat every remaining opponent (TP.md §3.1), approximated as the
  product of the equities against each opponent's public range (independence assumption: the
  opponents' hands are not removed from each other). Shown on a k-step quantile scale over the
  acting seat's possible combos, as in E1/E2.
- pot odds: to_call / (pot + to_call), steps 0 (nothing to call), <20%, <30%, <40%, >=40%.
- SPR: effective stack / pot, steps <1, <3, <6, >=6 (preflop: one value).

Every feature except hand.equity is public, so one key covers the same TP situation reached by
different histories — that is the "condition-insensitive" requirement (CHARTER), checked by Gate S.
Public ranges are each seat's reach probability over the 1326 combos, Bayes-updated from that
seat's own strategy at each public action (no hidden cards).
"""
from __future__ import annotations

import numpy as np

from stalker.e2.abstraction import quantile_buckets
from stalker.e2.eq_view import N, combo_index, equity_vs
from stalker.e3 import game as G

TIER_K = {"beginner": 5, "mid": 11}
AGGRESSIVE = ("r", "b33", "b75", "a")
POT_ODDS_EDGES = (0.2, 0.3, 0.4)
SPR_EDGES = (1.0, 3.0, 6.0)


def initial_ranges(n: int) -> list[np.ndarray]:
    return [np.ones(N) for _ in range(n)]


def _streets(history: tuple[str, ...]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for h in history:
        if h == "/":
            out.append([])
        else:
            out[-1].append(h)
    return out


def initiative(s: G.State, seat: int) -> int:
    # An all-in that only calls is also labelled "a" and counts as aggression here; that only
    # coarsens the key.
    if s.street == 0:
        return 0
    last = None
    for h in _streets(s.history)[s.street - 1]:
        p, a = h.split(":")
        if a in AGGRESSIVE:
            last = int(p)
    return 0 if last is None else 1 if last == seat else 2


def raise_level(s: G.State) -> int:
    return min(s.raises - 1 if s.street == 0 else s.raises, 3)


def pot_odds_step(s: G.State, seat: int) -> int:
    call = s.to_call(seat)
    if call <= 0:
        return 0
    ratio = call / (s.pot + call)
    return 1 + int(np.searchsorted(POT_ODDS_EDGES, ratio, side="right"))


def spr_step(s: G.State, seat: int) -> int:
    if s.street == 0:
        return 0
    others = [s.stack[i] for i in s.live() if i != seat]
    eff = min(s.stack[seat], max(others) if others else 0)
    return int(np.searchsorted(SPR_EDGES, eff / max(s.pot, 1), side="right"))


def multi_equity(s: G.State, seat: int, ranges: list[np.ndarray]) -> np.ndarray:
    """P(beat all remaining opponents) for every combo of `seat` (nan on board collisions)."""
    eq = np.ones(N)
    for q in s.live():
        if q != seat:
            eq = eq * equity_vs(tuple(s.board), ranges[q])
    return eq


def equity_steps(s: G.State, seat: int, ranges: list[np.ndarray], k: int) -> np.ndarray:
    eq = multi_equity(s, seat, ranges)
    live = ~np.isnan(eq)
    return quantile_buckets(np.nan_to_num(eq), live.astype(float), k)


def public_key(s: G.State, seat: int) -> str:
    n_opp = min(len(s.live()) - 1, 3)
    return (f"{seat}|{s.street}|{n_opp}|{raise_level(s)}|{initiative(s, seat)}|"
            f"{pot_odds_step(s, seat)}|{spr_step(s, seat)}|{''.join(G.legal(s))}")


def key(public: str, step: int) -> str:
    return f"{public}|e{step}"


def theoretical_keys(n: int, k: int) -> int:
    """Upper bound on keys per tier (legal-action sets aside): pos x street x n_opp x raise level x
    initiative x pot odds x SPR x equity steps."""
    return n * 4 * 3 * 4 * 3 * (1 + len(POT_ODDS_EDGES) + 1) * (len(SPR_EDGES) + 1) * k


def my_step(steps: np.ndarray, s: G.State, seat: int) -> int:
    return int(steps[combo_index(s.hole[seat])])
