"""Gate T2: computed TP items agree with their definitions (referee/GATES.md Gate T, docs/TP.md §3·§5).

For each recorded decision, every computed item the policy emits is recomputed from the policy's own
judgment items (the chained grading ① of TP.md §5: recompute from the earlier answers, not from the
truth) and the public facts, then compared within the spec tolerance `grading.t2_tolerance`.

Recomputation sources, chosen to stay exact or independent where the cost allows:
- `hand.equity` preflop, heads-up: the referee's class-vs-class table (`referee.anchors.hu_equity`,
  card removal through the exact pair counts) weighted by `opp.range`. Preflop TP values are per hand
  class, so the class average is the definition here.
- `hand.equity` preflop, multiway, `opp.range` absent: the product's equity-vs-n-random-hands table
  (`stalker.core.ranges.class_equity`). Not independent: it checks the chain (opponent count, range),
  not the table. A non-uniform multiway range is unsupported.
- `hand.equity` postflop and `hand.outs`/`hand.vuln`, heads-up: `stalker.tp.reference` (exact
  enumeration) against `opp.range`. Slow on the flop with wide ranges; quick runs only see what the
  registered policies emit.
An absent `opp.range` means the uniform prior (every live combo). A computed item T2 cannot recompute
(it needs TeacherContext assumptions, or multiway enumeration) fails with "unsupported" instead of
passing silently: extend this module in the same referee-change PR that makes a policy emit it.
"""
from __future__ import annotations

import numpy as np

from referee.anchors import hu_equity
from stalker.core.cards import COMBOS, HAND_CLASSES, card, hand_class
from stalker.core.ranges import class_equity, preflop_equity
from stalker.env.contract import PublicObservation
from stalker.tp import reference
from stalker.tp.spec import Spec

T2_DECISIONS = 8
CLASS_INDEX = {c: i for i, c in enumerate(HAND_CLASSES)}


def tolerance(spec: Spec, item: str) -> float:
    tol = spec.data["grading"].get("t2_tolerance")
    scale = spec.item(item)["scale"]
    if not tol or scale not in tol:
        raise KeyError(f"spec {spec.version} grading.t2_tolerance has no entry for scale {scale!r}; add one "
                       "(stalker/tp/spec, referee-change)")
    return float(tol[scale])


def _opponents(po: PublicObservation) -> int:
    return sum(1 for k, s in enumerate(po.seats) if k != 0 and s.used and s.in_hand)


def _range_weights(tp) -> np.ndarray | None:
    """Per class weight 0-1 from `opp.range` (None = uniform prior)."""
    r = tp.get("opp.range")
    return None if r is None else np.asarray(r, dtype=float) / 100.0


def _combo_range(weights: np.ndarray | None, dead: set[int]) -> list[tuple[tuple[int, int], float]]:
    out = []
    for a, b in COMBOS:
        if a in dead or b in dead:
            continue
        w = 1.0 if weights is None else float(weights[CLASS_INDEX[hand_class(a, b)]])
        if w > 0:
            out.append(((a, b), w))
    return out


def recompute(item: str, tp, po: PublicObservation) -> float | str:
    """The item's value from the TP judgments and public facts, or a reason string if unsupported."""
    hero = tuple(card(c) for c in po.hole_cards)
    board = tuple(card(c) for c in po.board)
    n = _opponents(po)
    w = _range_weights(tp)
    if item == "hand.equity" and not board:
        cls = hand_class(*hero)
        if n == 1:
            e, pairs = hu_equity.load()
            i = CLASS_INDEX[cls]
            wt = pairs[i] * (1.0 if w is None else w)
            if wt.sum() == 0:
                return "opp.range has no live combo"
            return 100.0 * float((e[i] * wt).sum() / wt.sum())
        if w is None and n <= len(preflop_equity()[cls]):
            return 100.0 * class_equity(cls, n)
        return f"preflop hand.equity against {n} opponents with a non-uniform opp.range or beyond the table"
    if n != 1:
        return f"{item} postflop multiway (exact enumeration over {n} ranges is too slow)"
    rng = _combo_range(w, set(hero) | set(board))
    if item == "hand.equity":
        return 100.0 * reference.equity(hero, board, [rng])["equity"]
    if item in ("hand.outs", "hand.vuln") and len(board) in (3, 4):
        return reference.next_card_shift(hero, board, [rng])[item.split(".")[1]]
    return f"{item} needs assumptions outside the TP vector (TeacherContext policy) or this street"


def check_t2(agent, observations: list[PublicObservation] | None = None) -> tuple[int, int, list[str]]:
    """Returns (passed, total, failures); one check per (decision, emitted computed item)."""
    from referee.gate_t import _decisions_with

    spec = agent.spec
    computed = [i["id"] for i in spec.data["items"] if i["kind"] == "computed"]
    pos = observations if observations is not None else _decisions_with(agent, computed, T2_DECISIONS)
    passed = total = 0
    failures = []
    for po in pos:
        tp = agent.tp(po)
        for item in computed:
            v = tp[item]
            if v is None:
                continue
            total += 1
            ref = recompute(item, tp, po)
            if isinstance(ref, str):
                failures.append(f"T2: hand {po.hand_id} {item}: unsupported ({ref}). Extend referee/gate_t/t2.py "
                                "before a registered policy emits this item.")
                continue
            tol = tolerance(spec, item)
            if abs(float(v) - ref) <= tol:
                passed += 1
            else:
                failures.append(f"T2: hand {po.hand_id} {item} = {float(v):.2f}, definition gives {ref:.2f} "
                                f"(tolerance {tol:g}). Compute it from the TP judgments and facts as docs/TP.md §3 "
                                "defines (opponent count, opp.range).")
    return passed, total, failures
