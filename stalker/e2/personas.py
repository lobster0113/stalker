"""Persona field for E2 (#226): the #198 rule-bot styles as E2 policies, league member 4.

A persona is a callable `state -> action probabilities over G.legal(state)`, usable wherever an E2
policy is (`referee.e2.exploiter.head_to_head`, the exploiter's fixed seat). It reads only its own
cards and the public state and is deterministic (mixing is in the returned probabilities).

Same four parameters and presets as `stalker.agents.persona`, mapped onto the E2 action menu:
- preflop, unraised: raise the top `pfr` of hands, call/check down to `vpip`, fold the rest;
  facing a raise: re-raise a third of the raise range, call 60% of the vpip range.
- postflop, by equity against a random hand (`ehs_table`): strong (>= 0.75) value-bets with
  probability `aggression`, medium bets small half as often, weak bluffs a third as often; facing a
  bet, strong raises half of `aggression`, medium calls, weak folds with probability `fold_to_bet`.
The VPIP targets are 6-max calibrated, so heads-up they read as styles, not frequencies.
Hand-written rules are only ever baselines and personas, never the TP-GTO (user requirement).
"""
from __future__ import annotations

import numpy as np

from stalker.agents.persona import PRESETS, PersonaParams
from stalker.core.cards import COMBO_INDEX
from stalker.core.ranges import hand_top_pct
from stalker.e2 import game as G
from stalker.e2.abstraction import ehs_table

STRONG, MEDIUM = 0.75, 0.5
# A label the menu does not offer at this node gives its weight to the next one that is offered.
FALLBACK = {"r": ("a", "c"), "b75": ("b33", "a", "k"), "b33": ("b75", "a", "k"), "a": ("r", "c"),
            "f": ("c", "k"), "c": ("k",), "k": ("c",)}


def _ehs(hole: tuple[int, int], board: tuple[int, ...]) -> float:
    a, b = hole
    return float(ehs_table(tuple(board))[COMBO_INDEX[(a, b) if a > b else (b, a)]])


def _to_probs(weights: dict[str, float], acts: list[str]) -> np.ndarray:
    out = np.zeros(len(acts))
    for label, w in weights.items():
        if w <= 0:
            continue
        for cand in (label, *FALLBACK.get(label, ())):
            if cand in acts:
                out[acts.index(cand)] += w
                break
    return out / out.sum()


class Persona:
    def __init__(self, name: str, params: PersonaParams | None = None):
        self.name = name
        self.p = params or PRESETS[name]

    def __call__(self, s: G.State) -> np.ndarray:
        acts = G.legal(s)
        hole = s.hole[s.to_act]
        call = s.to_call()
        if s.street == 0:
            t = hand_top_pct(*hole)                      # 0 = best hand
            if s.raises <= 1:                            # unraised: SB first in, or BB after a limp
                w = {"r": 1.0} if t < self.p.pfr else {"c": 1.0} if t < self.p.vpip or call == 0 else {"f": 1.0}
            else:
                w = ({"r": 1.0} if t < self.p.pfr / 3 else {"c": 1.0} if t < 0.6 * self.p.vpip else {"f": 1.0})
            return _to_probs(w, acts)
        e, agg, ftb = _ehs(hole, s.board), self.p.aggression, self.p.fold_to_bet
        if call == 0:
            if e >= STRONG:
                w = {"b75": agg, "b33": (1 - agg) / 2, "k": (1 - agg) / 2}
            elif e >= MEDIUM:
                w = {"b33": agg / 2, "k": 1 - agg / 2}
            else:
                w = {"b33": agg / 3, "k": 1 - agg / 3}
        elif e >= STRONG:
            w = {"r": agg / 2, "c": 1 - agg / 2}
        elif e >= MEDIUM:
            w = {"c": 1.0}
        else:
            w = {"f": ftb, "c": 1 - ftb}
        return _to_probs(w, acts)


def field(names=None) -> list[Persona]:
    return [Persona(n) for n in (names or PRESETS)]
