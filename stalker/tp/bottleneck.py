"""TP bottleneck policy structure (docs/TP.md §1, Gate T1).

The action head sees exactly two things: a TP vector (one value per spec item, None when N/A) and
the DecisionContext. `BottleneckAgent` is the only composition allowed: observation -> TP head ->
TP vector, observation -> DecisionContext, then head(TP, DC) -> action distribution. Item and fact
lists come from the TP spec, so a new spec version changes the encoding without code edits.

`LinearBottleneck` is a minimal seeded numpy implementation to exercise the interface. It is not
the TP-GTO: the final policy must be learned by competing against other TP policies (self-play /
league), not written by hand.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from stalker.core.ranges import class_equity
from stalker.core.cards import card, hand_class
from stalker.env.contract import DecisionContext, PublicObservation, decision_context
from stalker.tp.spec import Spec, load

ACTIONS = ("fold", "call", "raise")
# Numeric DecisionContext facts the head reads; each must be a field of the spec's decision_context.
DC_NUMERIC = ("to_call", "pot", "effective_stack_bb", "spr", "required_equity", "position_vs_button",
              "opponents_to_act")
# How each spec scale is stored and encoded: (number of values, lowest, highest). Values are divided
# by 100 when encoded. range_169: one 0-100 cell per hand class (100 x line frequency, as
# stalker.tp.reference.opp_range); risk_premium_pp: ICM premium in percentage points.
SCALES = {"0-100": (1, 0.0, 100.0), "range_169": (169, 0.0, 100.0), "risk_premium_pp": (1, -100.0, 100.0)}


def tp_items(spec: Spec) -> list[str]:
    """Items that form the TP vector: judgments and computed items, not the decision or reflections."""
    return [i["id"] for i in spec.data["items"] if i["kind"] in ("judgment", "computed")]


def item_scale(spec: Spec, item: str) -> tuple[int, float, float]:
    scale = spec.item(item)["scale"]
    if scale not in SCALES:
        raise ValueError(f"TP spec {spec.version} item {item} has scale {scale!r} that the bottleneck cannot encode; "
                         f"add it to stalker/tp/bottleneck.py SCALES (known: {sorted(SCALES)})")
    return SCALES[scale]


def check_dc_fields(spec: Spec) -> None:
    missing = [f for f in DC_NUMERIC if f not in spec.data["decision_context"]]
    if missing:
        raise ValueError(f"DC_NUMERIC uses {missing}, which TP spec {spec.version} decision_context does not define; "
                         "drop them from DC_NUMERIC or add them to the spec (referee-change)")


def feature_count(spec: Spec) -> int:
    check_dc_fields(spec)
    return sum(item_scale(spec, i)[0] + 1 for i in tp_items(spec)) + len(DC_NUMERIC)


class TPVector(Mapping):
    """Immutable item -> value map over exactly the spec's TP items (None = N/A or not asked)."""

    def __init__(self, values: dict[str, float | None], spec: Spec):
        items = tp_items(spec)
        unknown = set(values) - set(items)
        if unknown:
            raise ValueError(f"TP vector has items not in spec {spec.version}: {sorted(unknown)}")
        self._v: dict[str, tuple[float, ...] | None] = {}
        self._width: dict[str, int] = {}
        for i in items:
            width, lo, hi = item_scale(spec, i)
            self._width[i] = width
            v = values.get(i)
            if v is None:
                self._v[i] = None
                continue
            xs = (float(v),) if width == 1 and not isinstance(v, (list, tuple, np.ndarray)) else tuple(float(x) for x in v)
            if len(xs) != width:
                raise ValueError(f"{i} needs {width} values on scale {spec.item(i)['scale']}, got {len(xs)}")
            if not all(lo <= x <= hi for x in xs):
                raise ValueError(f"{i} has a value outside {lo:g}..{hi:g} (scale {spec.item(i)['scale']})")
            self._v[i] = xs
        self.spec_version = spec.version
        self._spec = spec

    def __getitem__(self, k):
        """A float for one-value scales, a tuple for range_169, None when N/A."""
        v = self._v[k]
        return v if v is None or self._width[k] > 1 else v[0]

    def width(self, k) -> int:
        return self._width[k]

    def __iter__(self):
        return iter(self._v)

    def __len__(self):
        return len(self._v)

    def __eq__(self, other):
        return isinstance(other, TPVector) and self._v == other._v

    def __hash__(self):
        return hash(tuple(self._v.items()))


class ActionHead(Protocol):
    def act(self, tp: TPVector, dc: DecisionContext) -> dict[str, float]: ...


TPHead = Callable[[PublicObservation], TPVector]


def encode(tp: TPVector, dc: DecisionContext) -> np.ndarray:
    """Fixed-order features: per TP item its values/100 (169 for range_169) and a present flag, then
    numeric DC facts. Length = feature_count(spec)."""
    out: list[float] = []
    for i in tp:
        v = tp._v[i]
        out += [0.0] * tp.width(i) if v is None else [x / 100.0 for x in v]
        out.append(0.0 if v is None else 1.0)
    out += [float(getattr(dc, f)) for f in DC_NUMERIC]
    return np.array(out)


def _legal_softmax(logits: np.ndarray, dc: DecisionContext) -> dict[str, float]:
    legal = [a for a in ACTIONS if a in dc.legal_actions]
    z = np.array([logits[ACTIONS.index(a)] for a in legal])
    p = np.exp(z - z.max())
    p /= p.sum()
    return {a: float(x) for a, x in zip(legal, p)}


@dataclass
class LinearBottleneck:
    """Softmax over legal actions of a linear function of encode(tp, dc)."""

    weights: np.ndarray  # (len(ACTIONS), n_features)

    @classmethod
    def init(cls, spec: Spec, rng: np.random.Generator, scale: float = 0.1) -> "LinearBottleneck":
        return cls(rng.normal(0.0, scale, size=(len(ACTIONS), feature_count(spec))))

    def act(self, tp: TPVector, dc: DecisionContext) -> dict[str, float]:
        return _legal_softmax(self.weights @ encode(tp, dc), dc)


def public_head(spec: Spec) -> TPHead:
    """Minimal TP head: preflop `hand.equity` from the class-equity table (vs one random hand), rest N/A."""
    def head(po: PublicObservation) -> TPVector:
        vals: dict[str, float | None] = {}
        if not po.board:
            a, b = (card(c) for c in po.hole_cards)
            vals["hand.equity"] = 100.0 * class_equity(hand_class(a, b))
        return TPVector(vals, spec)
    return head


@dataclass
class BottleneckAgent:
    head: TPHead
    action_head: ActionHead
    spec: Spec

    def tp(self, po: PublicObservation) -> TPVector:
        return self.head(po)

    def action_distribution(self, po: PublicObservation, tp: TPVector | None = None) -> dict[str, float]:
        """Action distribution; `tp` overrides the head (Gate T1 fixes it to probe the bottleneck)."""
        return self.action_head.act(self.head(po) if tp is None else tp, decision_context(po))


def default_agent(seed: int = 0) -> BottleneckAgent:
    spec = load()
    return BottleneckAgent(public_head(spec), LinearBottleneck.init(spec, np.random.default_rng(seed)), spec)
