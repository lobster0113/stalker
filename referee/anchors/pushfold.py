"""Heads-up chip-EV push/fold Nash equilibrium (SB shoves or folds, BB calls or folds).

    python -m referee.anchors.pushfold      # regenerate data/pushfold.json

Model (all values in big blinds, chip EV, no ICM):
  * `stack` S is each player's stack before posting; the SB posts 0.5, the BB posts 1.
  * `ante` a is a BB ante of extra dead money (not taken from either stack; the BB loses it with the pot).
  * SB net: fold -0.5; shove and BB folds 1+a; shove and call E*(2S+a) - S, E = all-in equity.
  * BB net: fold after a shove -(1+a); call (1-E)*(2S+a) - S - a.
Hands are the 169 classes; card removal enters through the exact pair counts of `hu_equity`.
Strategies are solved by fictitious play on the 169-class game (mixed allowed), with the BB responding
to the SB's running average and vice versa, until the summed best-response gain is <= `TOL` bb/hand.
Known-result check: 10bb no-ante gives SB shove ~58% and BB call ~37% (see tests for the sources).
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np

from stalker.core.cards import HAND_CLASSES

from . import hu_equity

DATA = Path(__file__).resolve().parent / "data" / "pushfold.json"
STACKS = [0.5 * k for k in range(2, 51)]  # 1.0 .. 25.0
ANTES = (0.0, 1.0)
TOL = 0.01
SB_FOLD = -0.5
COMBOS_PER_CLASS = np.array([6 if len(c) == 2 else (4 if c[2] == "s" else 12) for c in HAND_CLASSES], dtype=float)


def _tables():
    e, n = hu_equity.load()
    p = n / n.sum()  # joint probability of (SB class, BB class)
    return np.asarray(e, dtype=float), p


def _payoffs(stack: float, ante: float):
    e, p = _tables()
    pot = 2 * stack + ante
    sb_call = e * pot - stack                      # SB net when called
    bb_gain_call = (1 - e) * pot - stack + 1.0     # BB call minus BB fold, given SB shoved
    return p, sb_call, bb_gain_call


def _sb_values(c, p, sb_call, ante):
    """Per SB class a: (EV of shoving, EV of folding) given BB call probabilities c. Weighted by P(a)."""
    pa = p.sum(axis=1)
    push = (p * (c[None, :] * sb_call + (1 - c[None, :]) * (1 + ante))).sum(axis=1)
    return push, SB_FOLD * pa


def _bb_gain(s, p, bb_gain_call):
    """Per BB class b: weighted gain of calling over folding given SB shove probabilities s."""
    return (p * s[:, None] * bb_gain_call).sum(axis=0)


def _sb_total(s, c, p, sb_call, ante):
    push, fold = _sb_values(c, p, sb_call, ante)
    return float((s * push + (1 - s) * fold).sum())


def exploitability(stack: float, ante: float, push: np.ndarray, call: np.ndarray) -> float:
    """Summed best-response gain (bb/hand) of both seats against the given strategies."""
    p, sb_call, bb_gain = _payoffs(stack, ante)
    pu, fo = _sb_values(call, p, sb_call, ante)
    sb_gain = float(np.maximum(pu, fo).sum()) - _sb_total(push, call, p, sb_call, ante)
    g = _bb_gain(push, p, bb_gain)
    bb_cur = float((call * g).sum())
    bb_gain_br = float(np.maximum(g, 0).sum()) - bb_cur  # BB value is zero-sum with SB; gains are additive
    return sb_gain + bb_gain_br


def solve(stack: float, ante: float = 0.0, tol: float = TOL / 5, max_iter: int = 200000):
    """Return (push, call, exploitability) arrays over HAND_CLASSES."""
    p, sb_call, bb_gain = _payoffs(stack, ante)
    s = np.full(169, 0.5)
    c = np.full(169, 0.5)
    for t in range(1, max_iter + 1):
        pu, fo = _sb_values(c, p, sb_call, ante)
        s_br = (pu > fo).astype(float)
        c_br = (_bb_gain(s, p, bb_gain) > 0).astype(float)
        s += (s_br - s) / (t + 1)
        c += (c_br - c) / (t + 1)
        if t % 50 == 0 and exploitability(stack, ante, s, c) <= tol:
            break
    return s, c, exploitability(stack, ante, s, c)


@lru_cache(maxsize=1)
def table() -> dict:
    return json.loads(DATA.read_text())


def strategy(stack: float, ante: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Cached equilibrium (push probs, call probs) for the nearest grid stack."""
    key = f"{min(STACKS, key=lambda x: abs(x - stack)):g}/{ante:g}"
    ent = table()["solutions"][key]
    return np.array(ent["push"]), np.array(ent["call"])


def frequencies(push: np.ndarray, call: np.ndarray) -> tuple[float, float]:
    """(SB shove frequency over all combos, BB call frequency vs. the SB shoving range)."""
    sb = float((push * COMBOS_PER_CLASS).sum() / 1326)
    _, n = hu_equity.load()
    w = push[:, None] * np.asarray(n, dtype=float)
    return sb, float((w.sum(axis=0) * call).sum() / w.sum())


def ev_loss(policy_fn: Callable[[str], float], stack: float, ante: float = 0.0) -> float:
    """bb/hand an SB policy (class name -> shove prob) loses against the Nash BB vs. its best response."""
    _, call = strategy(stack, ante)
    p, sb_call, _ = _payoffs(min(STACKS, key=lambda x: abs(x - stack)), ante)
    pu, fo = _sb_values(call, p, sb_call, ante)
    pol = np.array([float(policy_fn(c)) for c in HAND_CLASSES])
    if ((pol < 0) | (pol > 1)).any():
        raise ValueError("policy_fn must return a probability in [0, 1]")
    return float(np.maximum(pu, fo).sum() - (pol * pu + (1 - pol) * fo).sum())


def main() -> int:
    sols = {}
    for ante in ANTES:
        for s in STACKS:
            push, call, ex = solve(s, ante)
            sols[f"{s:g}/{ante:g}"] = {
                "push": np.round(push, 4).tolist(), "call": np.round(call, 4).tolist(), "exploitability": round(ex, 5),
            }
            print(f"stack={s:g} ante={ante:g} expl={ex:.5f}", file=sys.stderr)
    DATA.write_text(json.dumps({"classes": HAND_CLASSES, "tol": TOL, "solutions": sols}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
