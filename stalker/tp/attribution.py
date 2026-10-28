"""Which TP judgments drove a decision, and where the decision would flip (#134).

The action head sees only the TP vector and the DecisionContext (Gate T1), so an explanation can be
stated in TP items alone. Definitions (fixed here, ADR 0011 references them):

- contribution of item i = total-variation distance between the action distribution at the user's
  TP vector and at the same vector with item i moved one tier step down or up (the larger of the
  two; clipped to the item's scale). An item the head does not read has contribution 0.
- threshold of item i = the value nearest to the current one, scanning in steps of 1, at which the
  most likely action changes, with the new action. None if no value on the scale changes it.

Only answered items on one-value scales are explained (`opp.range`'s 169 cells have no single step).
"""
from __future__ import annotations

from dataclasses import dataclass

from stalker.env.contract import DecisionContext
from stalker.tp.bottleneck import ActionHead, TPVector, item_scale


def tv(p: dict[str, float], q: dict[str, float]) -> float:
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


def _with(tp: TPVector, item: str, value: float) -> TPVector:
    _, lo, hi = item_scale(tp._spec, item)
    vals = dict(tp.items())
    vals[item] = min(hi, max(lo, value))
    return TPVector(vals, tp._spec)


def _top(d: dict[str, float]) -> str:
    return max(sorted(d), key=lambda a: d[a])


@dataclass(frozen=True)
class Attribution:
    item: str
    contribution: float          # 0..1 total-variation distance for a one-step change
    threshold: float | None      # nearest value where the top action changes
    flips_to: str | None         # the action at that threshold
    below: bool = False          # the flip happens when the value drops to the threshold


def attribute(head: ActionHead, tp: TPVector, dc: DecisionContext, step: float = 10.0) -> list[Attribution]:
    """Attributions for every answered item, largest contribution first."""
    base = head.act(tp, dc)
    top = _top(base)
    out = []
    for item, v in tp.items():
        if v is None or tp.width(item) > 1:   # one-value scales only; a 169-cell range has no single step
            continue
        _, lo, hi = item_scale(tp._spec, item)
        contrib = max(tv(base, head.act(_with(tp, item, v - step), dc)),
                      tv(base, head.act(_with(tp, item, v + step), dc)))
        thr = flip = None
        below = False
        for d in range(1, int(hi - lo) + 1):
            for cand in (v - d, v + d):
                if lo <= cand <= hi:
                    a = _top(head.act(_with(tp, item, cand), dc))
                    if a != top:
                        thr, flip, below = float(cand), a, cand < v
                        break
            if thr is not None:
                break
        out.append(Attribution(item, round(contrib, 6), thr, flip, below))
    return sorted(out, key=lambda a: -a.contribution)


def explain(attrs: list[Attribution], names: dict[str, str] | None = None, k: int = 3) -> list[str]:
    """Short sentences for the top-k drivers, e.g. "에퀴티 감각: 37 이하이면 fold"."""
    names = names or {}
    lines = []
    for a in attrs[:k]:
        if a.contribution == 0:
            break
        nm = names.get(a.item, a.item)
        if a.threshold is None:
            lines.append(f"{nm}: 결정에 영향 {a.contribution:.0%}")
        else:
            lines.append(f"{nm}: {a.threshold:g} {'이하' if a.below else '이상'}이면 {a.flips_to}")
    return lines
