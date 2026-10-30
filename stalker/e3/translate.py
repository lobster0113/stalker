"""Off-menu size translation (TP.md section 6, #382): any bet or raise maps to the two neighbouring menu sizes.

A person (or a bot) may bet or raise to any street total from the minimum raise to all in; the policy
table knows only the menu. Sizes are measured as x = (to - current bet) / (pot + to call), the bet as a
fraction of the pot after calling. Between the neighbouring menu sizes A < B (fractions a < b) the
pseudo-harmonic mapping (Ganzfried & Sandholm 2013) gives A the probability

    f = (b - x)(1 + a) / ((b - a)(1 + x))

and B the rest. It is the split that makes a hand indifferent between calling A and B in the
mapping's model; nearest-size rounding is exploitable (a size just past the midpoint buys the reading
of the larger bet at a smaller price). An exact menu size maps to itself, a size below the smallest
menu size maps to it, all in is "a" (all in is also the top neighbour when the stack lies above the
largest size). Only legal labels compete, so a capped street maps every size to the all-in.

`split` is the deterministic probability split (grading uses it as a weighted score); `sample` draws
one label from it with an explicit seeded Generator (the AI's reading of a hero's size), so a fixed
seed replays the same hand and the mapping cannot be gamed by sizing just past a fixed threshold.

`high_translation_error` (#417) marks the sizes whose split is a poor reading (pre-registered rule below,
mapped by stalker/tools/translation_map.py); grading shows such a size as approximate, not as a full score.
"""
from __future__ import annotations

import numpy as np

from stalker.e3 import game as G


def pot_fraction(s: G.State, to: int) -> float:
    """x of the mapping: chips above the current bet over the pot after calling."""
    return (to - max(s.bet)) / (s.pot + s.to_call())


def _menu(s: G.State) -> list[tuple[str, int]]:
    room = s.stack[s.to_act] + s.bet[s.to_act]
    legal = set(G.legal(s))
    out = [(a, to) for a, to in G._offered(s) if a in legal]
    if "a" in legal:
        out.append(("a", room))
    return sorted(out, key=lambda m: m[1])


def split(s: G.State, to: int) -> list[tuple[str, float]]:
    """[(label, probability)] for a bet or raise to `to` chips on this street (s = state before it)."""
    p = s.to_act
    room = s.stack[p] + s.bet[p]
    call = s.to_call()
    if s.done or s.stack[p] <= call or G._locked(s, p) or not G._can_cover(s):
        raise ValueError(f"no bet or raise possible after {s.history}; legal: {G.legal(s)}")
    least = min(max(s.bet) + s.last_raise, room)
    if to > room:
        raise ValueError(f"bet to {to} is more than all in ({room}); choose {least} (min raise) to {room}")
    if to < least:
        raise ValueError(f"bet to {to} is below the min raise {least}; choose {least} to {room} (all in)")
    menu = _menu(s)
    for a, t in menu:
        if t == to:
            return [(a, 1.0)]
    if to < menu[0][1]:
        return [(menu[0][0], 1.0)]
    j = next(i for i, (_, t) in enumerate(menu) if t > to)
    (la, ta), (lb, tb) = menu[j - 1], menu[j]
    a, b, x = pot_fraction(s, ta), pot_fraction(s, tb), pot_fraction(s, to)
    f = (b - x) * (1 + a) / ((b - a) * (1 + x))
    return [(la, f), (lb, 1.0 - f)]


def sample(s: G.State, to: int, rng: np.random.Generator) -> str:
    """One label drawn from `split` with the caller's seeded Generator."""
    out = split(s, to)
    if len(out) == 1:
        return out[0][0]
    return out[0][0] if rng.random() < out[0][1] else out[1][0]



# Pre-registered high-translation-error rule (#417), fixed before any grading change used it. Calibrated
# with `python -m stalker.tools.translation_map` on the served mid-6 table (v1 menu; local run, reference
# only): non-all-in neighbours whose pot fractions differ by more than GAP_HIGH (b33|b75, ratio 2.27) had
# a per-hand response TV of 0.32-0.38 on three flops, above TV_HIGH, and no point inside F_BAND with TV
# at or above TV_HIGH went unflagged. Every real-menu pair is at most 1.65 apart, so the gap rule flags
# none of them; the all-in rule still does above the largest size. The rule reads only the state, so
# Python and the page (web/app/tpgto.js translationError) agree without the policy table.
TV_HIGH = 0.25         # a reading is unreliable when 1 hand in 4 or more would answer A and B differently
GAP_HIGH = 2.0         # pot-fraction ratio b / a of the two neighbours that stands in for TV >= TV_HIGH
F_BAND = (0.2, 0.8)    # "far from both": neither neighbour holds 80% or more of the split


def high_translation_error(s: G.State, to: int) -> bool:
    """True when the split of a bet/raise to `to` is not a trustworthy reading (TP.md section 6 split):
    one neighbour is the all-in and the other is not, with `to` below ALLIN_MERGE of the stack (an all-in
    reading of a non-all-in size changes what the next seats may do, whatever its weight); or the size is
    far from both neighbours (F_BAND) and they are more than GAP_HIGH apart as pot fractions."""
    out = split(s, to)
    if len(out) < 2:
        return False
    (la, f), (lb, _) = out
    p = s.to_act
    if lb == "a":
        return to < G.ALLIN_MERGE * (s.stack[p] + s.bet[p])
    if not F_BAND[0] < f < F_BAND[1]:
        return False
    menu = dict(_menu(s))
    return pot_fraction(s, menu[lb]) > GAP_HIGH * pot_fraction(s, menu[la])
