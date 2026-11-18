"""Tournament reward for an E3 hand: prize-equity change instead of chip change (#879, ADR 0026 (b)).

The reward of a finished hand is E(after) - E(before) per seat, where E is
`stalker.core.icm.bubble_corrected_equity` (ICM plus the bubble correction `lam`, 0 = pure ICM).
Training-loop wiring, env_id and the choice of `lam` (#877) are separate issues.

Scope: exact ICM, so this is only correct when the hand's table is the whole remaining tournament
(one table, every stack known) with at most `MAX_EXACT_PLAYERS` live players.
"""
from __future__ import annotations

import numpy as np

from stalker.core.icm import MAX_EXACT_PLAYERS, bubble_corrected_equity
from stalker.e3.game import State, payoff


def tournament_payoff(state: State, table_stacks, payouts, lam: float = 0.0) -> np.ndarray:
    """Prize-equity change per table entry for the finished hand `state`.

    `table_stacks`: integer chip stacks of every entry of the table before the hand (before the
    blinds). Entries with 0 are players busted in earlier hands (they get reward 0); the non-zero
    entries, in order, are the hand's seats 0..n-1 and must equal each seat's starting stack.
    `payouts`: the tournament's prizes by finishing place (full list, not only the remaining ones;
    busted players took the bottom places). Returns a float array of len(table_stacks), in
    `payouts` units, summing to 0: a player busted in this hand is credited with the prize of the
    place they finish (several busting together: larger starting stack finishes higher, equal
    starting stacks share their places' prizes), so the prize pool is conserved.
    """
    t = np.asarray(table_stacks)
    if t.ndim != 1 or not np.issubdtype(t.dtype, np.integer) or np.any(t < 0):
        raise ValueError(f"table_stacks={table_stacks!r}: need a 1-D list of non-negative integer "
                         "chip stacks (0 = busted earlier).")
    seats = np.flatnonzero(t > 0)
    if seats.size > MAX_EXACT_PLAYERS:
        raise ValueError(f"{seats.size} live players exceed the exact ICM limit {MAX_EXACT_PLAYERS}: "
                         "tournament_payoff is for one final table; use chip payoff (or "
                         "stalker.core.icm.icm_equity_mc) for larger fields.")
    start = [state.stack[i] + state.total[i] for i in range(state.n)]
    if seats.size != state.n or [int(x) for x in t[seats]] != start:
        raise ValueError(f"table_stacks {t.tolist()} do not match the hand's starting stacks {start}: "
                         "pass every table entry's stack before the blinds, 0 only for busted players.")
    p = np.asarray(payouts, dtype=float)
    before = t.astype(np.int64)
    after = before.copy()
    after[seats] += payoff(state)
    e_before = np.asarray(bubble_corrected_equity(before, p, lam), dtype=float)
    e_after = np.zeros(t.size)
    if np.any(after > 0):
        e_after = np.asarray(bubble_corrected_equity(after, p, lam), dtype=float)
    _credit_busted(e_after, before, after, p)
    return e_after - e_before


def _credit_busted(e_after: np.ndarray, before: np.ndarray, after: np.ndarray, p: np.ndarray) -> None:
    busted = [i for i in range(before.size) if before[i] > 0 and after[i] == 0]
    if not busted:
        return
    place = int(np.count_nonzero(after > 0))         # 0-based place of the best newly busted player
    prize = np.concatenate([p, np.zeros(before.size)])
    for stack in sorted({int(before[i]) for i in busted}, reverse=True):
        group = [i for i in busted if before[i] == stack]
        share = prize[place:place + len(group)].sum() / len(group)
        e_after[group] = share
        place += len(group)
