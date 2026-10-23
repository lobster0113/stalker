"""Card representation.

A card is an int in [0, 52): rank = card >> 2 (0 = deuce .. 12 = ace), suit = card & 3.
"""
from __future__ import annotations

from itertools import combinations

RANKS = "23456789TJQKA"
SUITS = "cdhs"

N_CARDS = 52


def card(text: str) -> int:
    """'As' -> int."""
    return (RANKS.index(text[0].upper()) << 2) | SUITS.index(text[1].lower())


def cards(text: str) -> list[int]:
    """'AsKd 7c' -> [ints]."""
    text = text.replace(" ", "")
    return [card(text[i:i + 2]) for i in range(0, len(text), 2)]


def card_str(c: int) -> str:
    return RANKS[c >> 2] + SUITS[c & 3]


def cards_str(cs) -> str:
    return "".join(card_str(c) for c in cs)


def rank(c: int) -> int:
    return c >> 2


def suit(c: int) -> int:
    return c & 3


# All 1326 two-card combos, as (hi, lo) with hi > lo. Index is stable.
COMBOS: list[tuple[int, int]] = [(b, a) for a, b in combinations(range(N_CARDS), 2)]
COMBO_INDEX: dict[tuple[int, int], int] = {c: i for i, c in enumerate(COMBOS)}


def combo_index(c1: int, c2: int) -> int:
    return COMBO_INDEX[(c1, c2) if c1 > c2 else (c2, c1)]


def hand_class(c1: int, c2: int) -> str:
    """Canonical 169-class name: 'AA', 'AKs', 'T9o'."""
    r1, r2 = rank(c1), rank(c2)
    if r1 < r2:
        r1, r2 = r2, r1
    if r1 == r2:
        return RANKS[r1] * 2
    return RANKS[r1] + RANKS[r2] + ("s" if suit(c1) == suit(c2) else "o")


def all_hand_classes() -> list[str]:
    out = []
    for r1 in range(12, -1, -1):
        for r2 in range(r1, -1, -1):
            if r1 == r2:
                out.append(RANKS[r1] * 2)
            else:
                out.append(RANKS[r1] + RANKS[r2] + "s")
                out.append(RANKS[r1] + RANKS[r2] + "o")
    return out


HAND_CLASSES: list[str] = all_hand_classes()
COMBO_CLASS: list[str] = [hand_class(a, b) for a, b in COMBOS]
