"""6-max preflop charts from an E3 TP-key policy, in the strategy browser's spot format (#189, #196).

The policy acts on TP keys (position group, opponents, raise, pot odds, equity step), not on hand
classes, so a chart is derived: at each public preflop node, every combo of the acting seat gets
its equity step against the other seats' public ranges, the policy's action probabilities for that
step, and the per-class strategy is the reach-weighted average over the class's combos. Ranges
along the path are Bayes-updated with the same policy, exactly as in training.

These are approximate strategies of a policy still in training; the spot is marked `exact: false`
and carries the policy's N-seat LBR lower bound (Gate Q: only exactly solved spots are "GTO").
"""
from __future__ import annotations

from collections import deque

import numpy as np

from stalker.core.cards import COMBOS, HAND_CLASSES, hand_class
from stalker.e3 import game as G
from stalker.e3 import tp_key as K

CLASS_OF = np.array([HAND_CLASSES.index(hand_class(a, b)) for a, b in COMBOS])
CLASS_N = np.bincount(CLASS_OF, minlength=len(HAND_CLASSES)).astype(float)
LABEL = {"f": "Fold", "c": "Call", "r": "Raise", "a": "All-in", "k": "Check"}


def _public_root(n: int) -> G.State:
    # Hole cards do not enter public keys or ranges; a fixed deal keeps the chart deterministic.
    return G.deal(np.random.default_rng(0), n)


def _per_class(values: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Weighted per-class average of per-combo rows (values: (1326, m), weight: (1326,))."""
    num = np.zeros((len(HAND_CLASSES), values.shape[1]))
    np.add.at(num, CLASS_OF, values * weight[:, None])
    den = np.bincount(CLASS_OF, weight, len(HAND_CLASSES))
    out = np.divide(num, den[:, None], out=np.full_like(num, 1.0 / values.shape[1]), where=den[:, None] > 0)
    return out


def chart(policy: dict, k: int = 5, depth: str = "basic", n: int = 6, max_nodes: int = 60,
          lbr_bb: float | None = None, title: str | None = None) -> dict:
    names = list(G.position_names(n))
    nodes: dict[str, dict] = {}
    root = _public_root(n)
    queue = deque([("", root, K.initial_ranges(n))])
    decisions = 0
    while queue:
        nid, s, ranges = queue.popleft()
        if s.done or s.street > 0:
            nodes[nid] = {"terminal": "프리플랍 액션 종료 — 플랍으로" if not s.done else "핸드 종료"}
            continue
        if decisions >= max_nodes:
            nodes[nid] = {"terminal": "더 깊은 노드는 생략(표시 한도)"}
            continue
        decisions += 1
        p = s.to_act
        acts = G.legal(s)
        steps = K.equity_steps(s, p, ranges, k)
        public = K.public_key(s, p, depth)
        table = np.array([policy.get(K.key(public, v)) or [1.0 / len(acts)] * len(acts) for v in range(k)])
        if table.shape[1] != len(acts):
            table = np.full((k, len(acts)), 1.0 / len(acts))
        probs = table[np.maximum(steps, 0)]
        probs[steps < 0] = 0.0
        reach = {names[q]: np.round(_per_class(ranges[q][:, None], np.ones(len(COMBOS)))[:, 0], 3).tolist()
                 for q in range(n) if not np.all(ranges[q] == 1.0)}
        strat = np.round(_per_class(probs, ranges[p]), 3)
        nxt = {}
        for i, a in enumerate(acts):
            cid = f"{nid}-{p}{a}".lstrip("-")
            r = list(ranges)
            r[p] = ranges[p] * probs[:, i]
            nxt[LABEL.get(a, a)] = cid
            queue.append((cid, G.apply(s, a), r))
        nodes[nid] = {"seat": names[p], "actions": list(nxt), "next": nxt, "strategy": {"tp_beginner": strat.tolist()},
                      "reach": reach, "note": "TP 초보 키 정책(학습 중)에서 유도한 근사 전략"}
    return {"id": f"{n}max-100bb-tp", "title": title or f"{n}인 100BB 프리플랍 (TP 초보 정책, 근사)", "env": f"E3-{n}",
            "seats": names, "stack_bb": G.STACK // G.BB, "ante_bb": 0, "value_model": "chipev", "ev_unit": "bb",
            "exact": False, "exploitability": lbr_bb, "nodes": nodes}
