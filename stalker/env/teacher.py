"""Teacher labels computed from public observation + TeacherContext only (docs/TP.md §2)."""
from __future__ import annotations

import numpy as np

from stalker.core.cards import COMBOS, card, hand_class

from .contract import PublicObservation, TeacherContext


def opp_range_label(po: PublicObservation, teacher: TeacherContext, opponent_slot: int) -> np.ndarray:
    """P(opponent combo | public line, assumed opponent policy) over the 1326 combos.

    Uniform prior over combos not blocked by the hero's cards or the board; each public action of
    that opponent this hand multiplies in the assumed policy's probability for the combo's class.
    """
    dead = {card(c) for c in po.hole_cards + po.board}
    line = [a for slot, a, _ in po.history if slot == opponent_slot]
    w = np.zeros(len(COMBOS))
    for i, (a, b) in enumerate(COMBOS):
        if a in dead or b in dead:
            continue
        cls = hand_class(a, b)
        p = 1.0
        for act in line:
            p *= teacher.opponent_policy(cls, act)
        w[i] = p
    s = w.sum()
    if s == 0:
        raise ValueError("the assumed opponent policy never takes this public line; check TeacherContext")
    return w / s
