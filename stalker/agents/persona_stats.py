"""Measure a persona's realized style in a cash session (fidelity check for `PersonaParams`).

Definitions, per seat over all hands dealt to it:
- VPIP: share of hands where the seat voluntarily put chips in preflop (a call of a positive amount or a raise;
  the big blind's free check does not count).
- PFR: share of hands where the seat raised preflop at least once.
- aggression: postflop (bets+raises)/(bets+raises+calls), checks and folds excluded; `None` if the seat never bet/raised/called.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from stalker.agents.base import Agent, Event
from stalker.cash.presets import preset
from stalker.cash.session import run_cash_session


@dataclass(frozen=True)
class SeatStats:
    hands: int
    vpip: float
    pfr: float
    aggression: float | None


class _Counter:
    def __init__(self, seats: int) -> None:
        self.hands = [0] * seats
        self.vpip = [0] * seats
        self.pfr = [0] * seats
        self.aggr = [0] * seats
        self.calls = [0] * seats
        self._vpip_in: set[int] = set()
        self._pfr_in: set[int] = set()

    def __call__(self, event: Event) -> None:
        d = event.data
        if event.type == "NEW_HAND":
            self._vpip_in, self._pfr_in = set(), set()
            for s in d["seat_players"]:
                self.hands[s] += 1
        elif event.type == "ACTION":
            seat, kind = d["seat"], d["action"]
            if d["street"] == 0:
                if kind == "raise":
                    self._pfr_in.add(seat)
                if kind == "raise" or (kind == "call" and d["amount"] > 0):
                    self._vpip_in.add(seat)
            elif kind == "raise":
                self.aggr[seat] += 1
            elif kind == "call" and d["amount"] > 0:
                self.calls[seat] += 1
        elif event.type == "HAND_END" and "deltas" in d:
            for s in self._vpip_in:
                self.vpip[s] += 1
            for s in self._pfr_in:
                self.pfr[s] += 1


def measure_session(agents: Sequence[Agent], hands: int, seed: int, preset_name: str = "cash_6max_100bb") -> list[SeatStats]:
    """Play `hands` hands at a cash preset (seats = len(agents)) and report each seat's realized style."""
    cfg = preset(preset_name, hands=hands)
    counter = _Counter(cfg.seats)
    run_cash_session(cfg, agents, np.random.default_rng(seed), observer=counter)
    out = []
    for s in range(cfg.seats):
        n = counter.aggr[s] + counter.calls[s]
        out.append(SeatStats(counter.hands[s], counter.vpip[s] / counter.hands[s], counter.pfr[s] / counter.hands[s],
                             counter.aggr[s] / n if n else None))
    return out
