"""Monte Carlo equity of a hero hand against weighted opponent ranges."""
from __future__ import annotations

import numpy as np

from .cards import COMBOS, N_CARDS
from .evaluator import evaluate

N_COMBOS = len(COMBOS)
_COMBO_ARR = np.array(COMBOS, dtype=np.int64)


def blocked_mask(dead) -> np.ndarray:
    """Boolean mask over 1326 combos that conflict with any dead card."""
    dead = list(dead)
    if not dead:
        return np.zeros(N_COMBOS, dtype=bool)
    d = np.array(dead)
    return np.isin(_COMBO_ARR[:, 0], d) | np.isin(_COMBO_ARR[:, 1], d)


def equity_vs_ranges(hero, board, ranges, nsim: int, rng: np.random.Generator) -> float:
    """Hero equity (ties split) vs each opponent holding a hand drawn from its weight vector.

    `ranges` is a list of length-1326 non-negative weight arrays (one per opponent).
    """
    hero = list(hero)
    board = list(board)
    dead0 = set(hero) | set(board)
    blocked = blocked_mask(dead0)
    pools = []
    for w in ranges:
        w = np.where(blocked, 0.0, np.asarray(w, dtype=float))
        s = w.sum()
        if s <= 0:
            w = np.where(blocked, 0.0, 1.0)
            s = w.sum()
        pools.append(rng.choice(N_COMBOS, size=nsim * 3, p=w / s))
    need = 5 - len(board)
    live = [c for c in range(N_CARDS) if c not in dead0]
    total = 0.0
    done = 0
    ptr = [0] * len(pools)
    for _ in range(nsim):
        dead = set()
        opp_hands = []
        ok = True
        for k, pool in enumerate(pools):
            for _try in range(12):
                if ptr[k] >= len(pool):
                    ptr[k] = 0
                a, b = COMBOS[pool[ptr[k]]]
                ptr[k] += 1
                if a not in dead and b not in dead:
                    break
            else:
                ok = False
                break
            dead.add(a)
            dead.add(b)
            opp_hands.append((a, b))
        if not ok:
            continue
        if need:
            avail = [c for c in live if c not in dead]
            idx = rng.choice(len(avail), size=need, replace=False)
            runout = board + [avail[i] for i in idx]
        else:
            runout = board
        hs = evaluate(hero + runout)
        best = hs
        n_best = 1
        for a, b in opp_hands:
            s = evaluate([a, b] + runout)
            if s > best:
                best, n_best = s, 1
            elif s == best:
                n_best += 1
        if hs == best:
            total += 1.0 / n_best
        done += 1
    return total / done if done else 0.0
