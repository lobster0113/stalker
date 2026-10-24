"""Independent side-pot settlement for Gate R.

Written from the rules, not from the engine: contributions are layered by all-in level, each layer goes to
the best non-folded contributors that reached it, and odd chips go one at a time to winners in `order`.
"""
from __future__ import annotations

from typing import Mapping, Sequence


def settle(contrib: Mapping[int, int], folded: set[int], strength: Mapping[int, object],
           order: Sequence[int]) -> dict[int, int]:
    """Chips returned to each seat.

    contrib   total chips each seat put in (antes + bets); a layer only one seat reached is returned to it.
    folded    seats that gave up; their chips stay in the pot.
    strength  showdown key per live seat, larger wins (ties split); may be empty if a single seat is live.
    order     seats clockwise starting left of the button: the odd-chip order among tied winners.
    Adjacent layers with the same eligible seats are one pot, so odd chips are split once per pot.
    """
    live = [s for s in contrib if s not in folded and contrib[s] > 0]
    if not live:
        raise ValueError("no live seat with chips in the pot")
    pots: list[tuple[int, tuple[int, ...]]] = []
    prev = 0
    for level in sorted({c for c in contrib.values() if c > 0}):
        amount = sum(min(c, level) - min(c, prev) for c in contrib.values())
        eligible = tuple(s for s in live if contrib[s] >= level)
        prev = level
        if not eligible:  # only folded players reached this level: their chips join the pot below
            if not pots:
                raise ValueError("folded seats out-contributed every live seat")
            pots[-1] = (pots[-1][0] + amount, pots[-1][1])
        elif pots and pots[-1][1] == eligible:
            pots[-1] = (pots[-1][0] + amount, eligible)
        else:
            pots.append((amount, eligible))
    out = {s: 0 for s in contrib}
    for amount, eligible in pots:
        if len(eligible) == 1:
            out[eligible[0]] += amount
            continue
        best = max(strength[s] for s in eligible)
        winners = [s for s in order if s in eligible and strength[s] == best]
        share, odd = divmod(amount, len(winners))
        for i, s in enumerate(winners):
            out[s] += share + (1 if i < odd else 0)
    return out
