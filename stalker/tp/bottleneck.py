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
DC_NUMERIC = ("to_call", "pot", "effective_stack_bb", "spr", "required_equity", "position_vs_button",
              "opponents_to_act")


def tp_items(spec: Spec) -> list[str]:
    """Items that form the TP vector: judgments and computed items, not the decision or reflections."""
    return [i["id"] for i in spec.data["items"] if i["kind"] in ("judgment", "computed")]


class TPVector(Mapping):
    """Immutable item -> value map over exactly the spec's TP items (None = N/A or not asked)."""

    def __init__(self, values: dict[str, float | None], spec: Spec):
        items = tp_items(spec)
        unknown = set(values) - set(items)
        if unknown:
            raise ValueError(f"TP vector has items not in spec {spec.version}: {sorted(unknown)}")
        self._v = {i: (None if values.get(i) is None else float(values[i])) for i in items}
        for i, x in self._v.items():
            if x is not None and i != "plan.icm" and not 0.0 <= x <= 100.0:
                raise ValueError(f"{i}={x} is outside the 0-100 scale")
        self.spec_version = spec.version
        self._spec = spec

    def __getitem__(self, k):
        return self._v[k]

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
    """Fixed-order features: per TP item (value/100, present flag), then numeric DC facts."""
    out = []
    for i in tp:
        v = tp[i]
        out += [0.0 if v is None else v / 100.0, 0.0 if v is None else 1.0]
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
        n = 2 * len(tp_items(spec)) + len(DC_NUMERIC)
        return cls(rng.normal(0.0, scale, size=(len(ACTIONS), n)))

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
