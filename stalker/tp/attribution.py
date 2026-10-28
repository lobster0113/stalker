"""Which TP judgments drove a decision, and where the decision would flip (#134).

The action head sees only the TP vector and the DecisionContext (Gate T1), so an explanation can be
stated in TP items alone. Definitions:

- tier step: the spacing of the answers the user's tier can give (spec `tiers[t].steps`: beginner
  25, mid 10, pro 1). Items on another one-value scale (plan.icm, -100..100 pp) use the same
  spacing on their own range.
- contribution of item i = total-variation distance between the action distribution at the user's
  TP vector and at the same vector with item i moved one tier step down or up (the larger of the
  two; clipped to the item's scale). An item the head does not read has contribution 0.
- threshold of item i = the answerable value (on the tier's grid) nearest to the current one at
  which the most likely action changes, with the new action. None if no such value exists.

Only answered items on one-value scales are explained (`opp.range`'s 169 cells have no single step).
Total-variation sensitivity is used rather than Shapley values: one head call per neighbour instead
of 2^n coalitions, and it is read on the same axis as the threshold; it does not split credit for
interactions between items.
"""
from __future__ import annotations

from dataclasses import dataclass

from stalker.env.contract import DecisionContext
from stalker.tp.bottleneck import ActionHead, TPVector, item_scale


def tv(p: dict[str, float], q: dict[str, float]) -> float:
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


def _with(tp: TPVector, item: str, value: float) -> TPVector:
    _, lo, hi = item_scale(tp.spec, item)
    vals = dict(tp.items())
    vals[item] = min(hi, max(lo, value))
    return TPVector(vals, tp.spec)


def tier_step(spec, tier: str) -> float:
    """Answer spacing of a tier: the gap of its `steps` grid, or 1 for a continuous ("0-100") tier."""
    steps = spec.data["tiers"][tier]["steps"]
    return 1.0 if isinstance(steps, str) else float(steps[1] - steps[0])


def answer_grid(spec, tier: str, item: str) -> list[float]:
    """The values a user of this tier can give for the item: its scale in tier-step spacing."""
    _, lo, hi = item_scale(spec, item)
    step = tier_step(spec, tier)
    n = int(round((hi - lo) / step))
    return [lo + step * j for j in range(n + 1)]


def _top(d: dict[str, float]) -> str:
    return max(sorted(d), key=lambda a: d[a])


@dataclass(frozen=True)
class Attribution:
    item: str
    contribution: float          # 0..1 total-variation distance for a one-step change
    threshold: float | None      # nearest value where the top action changes
    flips_to: str | None         # the action at that threshold
    below: bool = False          # the flip happens when the value drops to the threshold


def attribute(head: ActionHead, tp: TPVector, dc: DecisionContext, tier: str = "pro") -> list[Attribution]:
    """Attributions for every answered one-value item, largest contribution first.

    Moves and thresholds follow the tier's answer grid (`tier_step`, `answer_grid`): a beginner's
    one step is 25 and a threshold is one of 0/25/50/75/100.
    """
    base = head.act(tp, dc)
    top = _top(base)
    step = tier_step(tp.spec, tier)
    out = []
    for item, v in tp.items():
        if v is None or tp.width(item) > 1:   # one-value scales only; a 169-cell range has no single step
            continue
        contrib = max(tv(base, head.act(_with(tp, item, v - step), dc)),
                      tv(base, head.act(_with(tp, item, v + step), dc)))
        thr = flip = None
        below = False
        for cand in sorted((g for g in answer_grid(tp.spec, tier, item) if g != v), key=lambda g: (abs(g - v), g)):
            a = _top(head.act(_with(tp, item, cand), dc))
            if a != top:
                thr, flip, below = float(cand), a, cand < v
                break
        out.append(Attribution(item, round(contrib, 6), thr, flip, below))
    return sorted(out, key=lambda a: -a.contribution)


def explain(attrs: list[Attribution], names: dict[str, str] | None = None, k: int = 3) -> list[str]:
    """Short sentences for the top-k drivers, e.g. "에퀴티 감각: 37 이하이면 fold"."""
    names = names or {}
    lines = []
    for a in [a for a in attrs if a.contribution > 0 or a.threshold is not None][:k]:
        nm = names.get(a.item, a.item)
        if a.threshold is None:
            lines.append(f"{nm}: 결정에 영향 {a.contribution:.0%}")
        else:
            lines.append(f"{nm}: {a.threshold:g} {'이하' if a.below else '이상'}이면 {a.flips_to}")
    return lines
