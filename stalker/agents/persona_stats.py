"""Measure a persona's realized style in a cash session (fidelity check for `PersonaParams`).

Definitions, per seat over all hands dealt to it:
- VPIP: share of hands where the seat voluntarily put chips in preflop (a call of a positive amount or a raise;
  the big blind's free check does not count).
- PFR: share of hands where the seat raised preflop at least once.
- aggression: postflop (bets+raises)/(bets+raises+calls), checks and folds excluded; `None` if the seat never bet/raised/called.
- flop/turn c-bet: of the times the last preflop raiser acts first-to-bet on that street (nobody bet yet), the share it bets.
  The turn c-bet includes a delayed bet after the flop was checked through.
- fold to flop c-bet: of the times a seat faces the preflop raiser's first flop bet (no raise in between), the share it folds.
- fold to turn c-bet: same as the flop version on the turn (the preflop raiser's first turn bet, no raise in between).
- fold to river bet: of the river decisions that face a bet (a fold, a call of a positive amount, or a raise over a bet), the share that fold.
- WTSD: of the hands where the seat saw the flop, the share where it showed down.
Every `None` below means the seat never had the opportunity.

`flop_cells` splits the flop c-bet and fold-to-flop-c-bet into the 4 cells of `stalker.tools.phh_stats`
(#627, #641) with the shared `flop_cell`: heads-up = 2 players saw the flop, 3-bet+ = 2 or more preflop
raises. Human targets differ a lot by cell, so a persona is compared cell by cell, not on the mixed total.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from stalker.agents.base import Agent, Event
from stalker.cash.presets import preset
from stalker.cash.session import run_cash_session


CELLS = ("hu_srp", "hu_3bp", "mw_srp", "mw_3bp")


def flop_cell(players_on_flop: int, preflop_raises: int) -> str:
    """Cell of a flop: heads-up (2 players) or multiway, single-raised (1 raise) or 3-bet+ (2 or more)."""
    return ("hu" if players_on_flop == 2 else "mw") + ("_srp" if preflop_raises == 1 else "_3bp")


@dataclass(frozen=True)
class CellStats:
    cbet: float | None
    cbet_opps: int
    fold_cbet: float | None
    fold_opps: int


@dataclass(frozen=True)
class SeatStats:
    hands: int
    vpip: float
    pfr: float
    aggression: float | None
    cbet_flop: float | None = None
    cbet_turn: float | None = None
    fold_cbet_flop: float | None = None
    fold_cbet_turn: float | None = None
    fold_river: float | None = None
    wtsd: float | None = None
    flop_cells: dict[str, CellStats] = field(default_factory=dict)


class _Counter:
    def __init__(self, seats: int) -> None:
        self.hands = [0] * seats
        self.vpip = [0] * seats
        self.pfr = [0] * seats
        self.aggr = [0] * seats
        self.calls = [0] * seats
        self.opp = {k: [0] * seats for k in ("cb1", "cb2", "fcb", "fct", "fr", "flop")}
        self.hit = {k: [0] * seats for k in ("cb1", "cb2", "fcb", "fct", "fr", "sd")}
        for k in (f"{b}_{c}" for c in CELLS for b in ("cb1", "fcb")):
            self.opp[k] = [0] * seats
            self.hit[k] = [0] * seats
        self._new_hand()

    def _new_hand(self) -> None:
        self._vpip_in: set[int] = set()
        self._pfr_in: set[int] = set()
        self._aggr: int | None = None  # last preflop raiser
        self._bets: dict[int, int] = {}  # street (board size 0/3/4/5) -> bets/raises so far
        self._first: dict[int, int] = {}  # street -> first bettor
        self._players: set[int] = set()
        self._folded_pre: set[int] = set()
        self._flop = False
        self._showdown: set[int] = set()
        self._pf_raises = 0
        self._cell = ""

    def __call__(self, event: Event) -> None:
        d = event.data
        if event.type == "NEW_HAND":
            self._new_hand()
            for s in d["seat_players"]:
                self.hands[s] += 1
                self._players.add(s)
        elif event.type == "ACTION":
            seat, kind, street = d["seat"], d["action"], d["street"]
            if street > 0:
                if not self._flop:
                    self._cell = flop_cell(len(self._players - self._folded_pre), self._pf_raises)
                self._flop = True
                self._postflop_action(seat, kind, street, d["amount"])
            elif kind == "fold":
                self._folded_pre.add(seat)
            if street == 0:
                if kind == "raise":
                    self._pf_raises += 1
                    self._pfr_in.add(seat)
                    self._aggr = seat
                if kind == "raise" or (kind == "call" and d["amount"] > 0):
                    self._vpip_in.add(seat)
            elif kind == "raise":
                self.aggr[seat] += 1
            elif kind == "call" and d["amount"] > 0:
                self.calls[seat] += 1
        elif event.type == "SHOWDOWN":
            self._showdown = set(d["hands"])
            self._flop = self._flop or len(d["board"]) >= 3
        elif event.type == "HAND_END" and "deltas" in d:
            if self._flop:
                for s in self._players - self._folded_pre:
                    self.opp["flop"][s] += 1
                    self.hit["sd"][s] += s in self._showdown
            for s in self._vpip_in:
                self.vpip[s] += 1
            for s in self._pfr_in:
                self.pfr[s] += 1

    def _postflop_action(self, seat: int, kind: str, street: int, amount: int = 0) -> None:
        n = self._bets.get(street, 0)
        if n == 0 and self._aggr == seat and street <= 4:  # first to bet on the street: a c-bet chance
            key = f"cb{street - 2}"
            self.opp[key][seat] += 1
            self.hit[key][seat] += kind == "raise"
            if street == 3:
                self.opp[f"cb1_{self._cell}"][seat] += 1
                self.hit[f"cb1_{self._cell}"][seat] += kind == "raise"
        elif n == 1 and street == 3 and self._first.get(3) == self._aggr and seat != self._aggr:
            self.opp["fcb"][seat] += 1  # faces the flop c-bet with no raise in between
            self.hit["fcb"][seat] += kind == "fold"
            self.opp[f"fcb_{self._cell}"][seat] += 1
            self.hit[f"fcb_{self._cell}"][seat] += kind == "fold"
        elif n == 1 and street == 4 and self._first.get(4) == self._aggr and seat != self._aggr:
            self.opp["fct"][seat] += 1
            self.hit["fct"][seat] += kind == "fold"
        if street == 5 and (kind == "fold" or (kind == "call" and amount > 0) or (kind == "raise" and n >= 1)):
            self.opp["fr"][seat] += 1
            self.hit["fr"][seat] += kind == "fold"
        if kind == "raise":
            self._bets[street] = n + 1
            self._first.setdefault(street, seat)


def _rate(c: _Counter, opp: str, hit: str, s: int) -> float | None:
    return c.hit[hit][s] / c.opp[opp][s] if c.opp[opp][s] else None


def _cells(c: _Counter, s: int) -> dict[str, CellStats]:
    return {cl: CellStats(_rate(c, f"cb1_{cl}", f"cb1_{cl}", s), c.opp[f"cb1_{cl}"][s],
                          _rate(c, f"fcb_{cl}", f"fcb_{cl}", s), c.opp[f"fcb_{cl}"][s]) for cl in CELLS}


def measure_session(agents: Sequence[Agent], hands: int, seed: int, preset_name: str = "cash_6max_100bb") -> list[SeatStats]:
    """Play `hands` hands at a cash preset (seats = len(agents)) and report each seat's realized style."""
    cfg = preset(preset_name, hands=hands)
    counter = _Counter(cfg.seats)
    run_cash_session(cfg, agents, np.random.default_rng(seed), observer=counter)
    out = []
    for s in range(cfg.seats):
        n = counter.aggr[s] + counter.calls[s]
        out.append(SeatStats(counter.hands[s], counter.vpip[s] / counter.hands[s], counter.pfr[s] / counter.hands[s],
                             counter.aggr[s] / n if n else None, _rate(counter, "cb1", "cb1", s),
                             _rate(counter, "cb2", "cb2", s), _rate(counter, "fcb", "fcb", s),
                             _rate(counter, "fct", "fct", s), _rate(counter, "fr", "fr", s),
                             _rate(counter, "flop", "sd", s), _cells(counter, s)))
    return out
