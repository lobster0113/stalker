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
    if s.done or s.stack[p] <= call or s.acted[p] or not [i for i in s.active() if i != p]:
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
