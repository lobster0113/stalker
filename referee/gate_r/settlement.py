"""Independent side-pot settlement for Gate R (no PokerKit, no stalker imports).

Written from the rules, not from the engine. Rules (referee/GATES.md, Gate R):
- Antes are dead money in the lowest pot: every live seat, even one all-in from the ante, can win them.
- Bets (blinds included) are layered by all-in level; a layer belongs to the live seats that reached it.
  Uncalled chips must already be refunded by the caller (`paid` is net of refunds).
- At showdown a live hand that cannot win any pot it contests is mucked first; then adjacent pots contested
  by the same seats are one pot.
- Ties split a pot evenly; all odd chips of a pot go to the first winner left of the button (TDA odd-chip
  rule with 1-chip denomination).
"""
from __future__ import annotations

from typing import Mapping, Sequence


def build_pots(paid: Mapping[int, int], antes: Mapping[int, int], contesting: set[int]) -> list[tuple[int, tuple[int, ...]]]:
    """Pots (amount, contesting seats), lowest first. Seats outside `contesting` only feed the pots."""
    contrib = {s: paid[s] - antes.get(s, 0) for s in paid}
    if any(c < 0 for c in contrib.values()):
        raise ValueError("a seat's antes exceed its total paid chips")
    pots: list[tuple[int, tuple[int, ...]]] = []
    amount = sum(antes.values())
    prev = 0
    for level in sorted(set(contrib.values()) | {0}):
        amount += sum(min(c, level) - min(c, prev) for c in contrib.values())
        prev = level
        players = tuple(sorted(s for s in contesting if contrib[s] >= level))
        if not amount:
            continue
        if not players:
            raise ValueError(f"{amount} chips above level {level} were reached only by folded seats; refund uncalled bets first")
        if pots and pots[-1][1] == players:
            amount += pots.pop()[0]
        pots.append((amount, players))
        amount = 0
    return pots


def settle(paid: Mapping[int, int], folded: set[int], strength: Mapping[int, object], order: Sequence[int],
           antes: Mapping[int, int] | None = None) -> dict[int, int]:
    """Chips each seat collects from the pot.

    paid      chips each seat put in this hand (antes + bets, net of uncalled refunds).
    folded    seats that gave up.
    strength  comparable showdown key per live seat, larger wins; unused when one seat is live.
    order     seats clockwise starting left of the button (odd-chip priority).
    antes     the part of `paid` that was an ante.
    """
    antes = dict(antes or {})
    live = {s for s in paid if s not in folded}
    if not live:
        raise ValueError("no live seat")
    out = {s: 0 for s in paid}
    total = sum(paid.values())
    if len(live) == 1:
        out[next(iter(live))] = total
        return out
    alive = {s for s in live
             if any(s in seats and all(strength[s] >= strength[o] for o in seats)
                    for _, seats in build_pots(paid, antes, live))}
    for amount, seats in build_pots(paid, antes, alive):
        best = max(strength[s] for s in seats)
        winners = [s for s in order if s in seats and strength[s] == best]
        share, odd = divmod(amount, len(winners))
        for s in winners:
            out[s] += share
        out[winners[0]] += odd
    return out
