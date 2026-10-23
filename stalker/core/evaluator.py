"""Fast-enough 5..7 card hand evaluator (pure Python, table driven).

Score is an int; higher is better. Layout: category << 20 | five 4-bit rank nibbles.
Categories: 0 high, 1 pair, 2 two pair, 3 trips, 4 straight, 5 flush, 6 full house,
7 quads, 8 straight flush.
"""
from __future__ import annotations

HIGH, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)
CATEGORY_NAMES = [
    "high_card", "pair", "two_pair", "trips", "straight",
    "flush", "full_house", "quads", "straight_flush",
]


def _build_tables():
    straight_high = [-1] * 8192
    top_ranks = [None] * 8192
    popcnt = [0] * 8192
    for m in range(8192):
        bits = [r for r in range(12, -1, -1) if m >> r & 1]
        top_ranks[m] = bits
        popcnt[m] = len(bits)
        best = -1
        for hi in range(12, 3, -1):
            need = 0b11111 << (hi - 4)
            if m & need == need:
                best = hi
                break
        if best < 0 and (m & 0b1000000001111) == 0b1000000001111:
            best = 3  # A-2-3-4-5, five-high
        straight_high[m] = best
    return straight_high, top_ranks, popcnt


_STRAIGHT_HIGH, _TOP_RANKS, _POPCNT = _build_tables()


def _kick(ranks) -> int:
    v = 0
    for i, r in enumerate(ranks[:5]):
        v |= r << (16 - 4 * i)
    return v


def evaluate(cards) -> int:
    rank_counts = [0] * 13
    suit_masks = [0, 0, 0, 0]
    for c in cards:
        r = c >> 2
        rank_counts[r] += 1
        suit_masks[c & 3] |= 1 << r

    for m in suit_masks:
        if _POPCNT[m] >= 5:
            sh = _STRAIGHT_HIGH[m]
            if sh >= 0:
                return (STRAIGHT_FLUSH << 20) | (sh << 16)
            return (FLUSH << 20) | _kick(_TOP_RANKS[m])

    quads = trips = -1
    trips2 = -1
    pairs = []
    singles_mask = 0
    rank_mask = 0
    for r in range(12, -1, -1):
        n = rank_counts[r]
        if n:
            rank_mask |= 1 << r
        if n == 4:
            quads = r
        elif n == 3:
            if trips < 0:
                trips = r
            elif trips2 < 0:
                trips2 = r
        elif n == 2:
            pairs.append(r)
        elif n == 1:
            singles_mask |= 1 << r

    if quads >= 0:
        kick = max(r for r in range(13) if rank_counts[r] and r != quads)
        return (QUADS << 20) | (quads << 16) | (kick << 12)
    if trips >= 0:
        pair_r = max(trips2, pairs[0] if pairs else -1)
        if pair_r >= 0:
            return (FULL_HOUSE << 20) | (trips << 16) | (pair_r << 12)
    sh = _STRAIGHT_HIGH[rank_mask]
    if sh >= 0:
        return (STRAIGHT << 20) | (sh << 16)
    if trips >= 0:
        k = _TOP_RANKS[singles_mask]
        return (TRIPS << 20) | (trips << 16) | (k[0] << 12) | (k[1] << 8)
    if len(pairs) >= 2:
        p1, p2 = pairs[0], pairs[1]
        rest = singles_mask | (1 << pairs[2] if len(pairs) > 2 else 0)
        k = _TOP_RANKS[rest][0]
        return (TWO_PAIR << 20) | (p1 << 16) | (p2 << 12) | (k << 8)
    if pairs:
        k = _TOP_RANKS[singles_mask]
        return (PAIR << 20) | (pairs[0] << 16) | (k[0] << 12) | (k[1] << 8) | (k[2] << 4)
    return (HIGH << 20) | _kick(_TOP_RANKS[singles_mask])


def category(score: int) -> int:
    return score >> 20
