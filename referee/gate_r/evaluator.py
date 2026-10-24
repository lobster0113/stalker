"""Independent 5-of-7 hand evaluator for Gate R (no PokerKit, no stalker imports)."""
from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Sequence

_RANKS = "23456789TJQKA"


def _score5(cards: Sequence[tuple[int, str]]) -> tuple:
    ranks = sorted((r for r, _ in cards), reverse=True)
    flush = len({s for _, s in cards}) == 1
    uniq = sorted(set(ranks), reverse=True)
    straight_high = None
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight_high = uniq[0]
        elif uniq == [12, 3, 2, 1, 0]:
            straight_high = 3  # wheel
    groups = sorted(Counter(ranks).items(), key=lambda kv: (-kv[1], -kv[0]))
    shape = [n for _, n in groups]
    tiebreak = tuple(r for r, _ in groups)
    if straight_high is not None and flush:
        return (8, straight_high)
    if shape == [4, 1]:
        return (7, *tiebreak)
    if shape == [3, 2]:
        return (6, *tiebreak)
    if flush:
        return (5, *ranks)
    if straight_high is not None:
        return (4, straight_high)
    if shape == [3, 1, 1]:
        return (3, *tiebreak)
    if shape == [2, 2, 1]:
        return (2, *tiebreak)
    if shape == [2, 1, 1, 1]:
        return (1, *tiebreak)
    return (0, *ranks)


def strength(hole: Sequence[str], board: Sequence[str]) -> tuple:
    """Comparable key for the best 5-card hand from `hole` + `board` ('As' style); larger wins."""
    cards = [(_RANKS.index(c[0].upper()), c[1].lower()) for c in (*hole, *board)]
    return max(_score5(c) for c in combinations(cards, 5))
