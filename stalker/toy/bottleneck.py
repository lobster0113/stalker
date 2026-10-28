"""TP bottleneck policies for the E0 toy games.

A bottleneck policy may only see a TP summary of its private information — a hand-strength bucket
(the toy analogue of `hand.equity`) — plus the public action history (the toy DecisionContext).
Infosets that share a summary are merged and CFR+ optimizes inside that constraint; the result is
mapped back to the full game, where `referee.anchors.toy.exploitability` measures it exactly. The
gap to the unconstrained CFR+ policy is the complexity cost of the bottleneck (Gate Q4 report).

Toy games are single hands, so the opponent-tendency items (`opp.*`) have nothing to observe; only
the hand-strength channel is constrained here.
"""
from __future__ import annotations

from collections.abc import Callable

import numpy as np

from referee.anchors.toy import kuhn, leduc
from referee.anchors.toy.game import PLAYER, Node, finalize, infosets

from .cfr import CFRPlus

KeyFn = Callable[[str], str]


def abstract(root: Node, key: KeyFn) -> Node:
    """Copy of the tree with every player infoset renamed by `key` (merging those that collide)."""
    def copy(n: Node) -> Node:
        return Node(n.kind, player=n.player, infoset=key(n.infoset) if n.kind == PLAYER else n.infoset,
                    actions=n.actions, children=[copy(c) for c in n.children], probs=n.probs,
                    utility=n.utility)
    return finalize(copy(root))


def lift(full_root: Node, abstract_strategy: dict, key: KeyFn) -> dict[str, list[float]]:
    """Strategy on the full game that plays the abstract strategy of each infoset's summary."""
    return {i: list(abstract_strategy[key(i)]) for i in infosets(full_root)}


def _buckets(strengths: dict[str, float], k: int) -> dict[str, int]:
    """Split distinct strength values into k contiguous groups (weakest = 0)."""
    levels = sorted(set(strengths.values()))
    k = max(1, min(k, len(levels)))
    group = {}
    for b, chunk in enumerate(np.array_split(np.array(levels), k)):
        for v in chunk:
            group[float(v)] = b
    return {h: group[v] for h, v in strengths.items()}


def kuhn_key(k: int) -> KeyFn:
    """Kuhn summary: card rank bucketed into k groups (k=3 is the full information)."""
    b = _buckets({c: float(i) for i, c in enumerate(kuhn.CARDS)}, k)

    def key(infoset: str) -> str:
        card, hist = infoset.split(":", 1)
        return f"b{b[card]}:{hist}"
    return key


def leduc_strength(private: str, public: str | None) -> float:
    """Showdown equity of a private card against a uniformly random remaining card (ties count half).
    This is the toy `hand.equity` against an unknown range; the bucket order is what matters.

    Uses only the player's own cards and the deck — public information, no opponent policy.
    """
    deck = list(leduc.DECK)
    p = leduc.RANKS.index(private)
    deck.remove(p)
    if public is not None:
        q = leduc.RANKS.index(public)
        deck.remove(q)
        win = sum(1.0 if leduc._showdown((p, o), q) > 0 else 0.5 if leduc._showdown((p, o), q) == 0 else 0.0
                  for o in deck)
        return win / len(deck)
    # Round 1: average over the public card still to come.
    vals = []
    for i, q in enumerate(deck):
        rest = deck[:i] + deck[i + 1:]
        vals.append(sum(1.0 if leduc._showdown((p, o), q) > 0 else 0.5 if leduc._showdown((p, o), q) == 0
                        else 0.0 for o in rest) / len(rest))
    return float(np.mean(vals))


def leduc_key(k1: int, k2: int) -> KeyFn:
    """Leduc summary: own-card strength bucket (k1 groups in round 1, k2 per board in round 2)
    + the public card + public history. The board and history are facts (DecisionContext); only
    the private card is hidden behind the strength summary, as in the real TP.
    """
    r1 = _buckets({c: leduc_strength(c, None) for c in leduc.RANKS}, k1)
    r2 = {d: _buckets({c: leduc_strength(c, d) for c in leduc.RANKS}, k2) for d in leduc.RANKS}

    def key(infoset: str) -> str:
        seen, hist = infoset.split(":", 1)
        if len(seen) == 1:
            return f"b{r1[seen]}:{hist}"
        return f"{seen[1]}b{r2[seen[1]][seen[0]]}:{hist}"
    return key


def solve(root: Node, key: KeyFn, iterations: int) -> dict[str, list[float]]:
    """CFR+ inside the bottleneck, returned as a full-game strategy."""
    solver = CFRPlus(abstract(root, key))
    solver.iterate(iterations)
    return lift(root, solver.average_strategy(), key)


KUHN_LEVELS = [(1,), (2,), (3,)]
LEDUC_LEVELS = [(1, 1), (2, 1), (3, 1), (1, 2), (2, 2), (3, 2), (1, 3), (2, 3), (3, 3)]


def curve(game: str, iterations: int) -> list[dict]:
    """Exploitability of the bottleneck policy at each summary resolution, plus the unconstrained one."""
    from referee.anchors.toy import exploitability

    root = {"kuhn": kuhn.game, "leduc": leduc.game}[game]()
    rows = []
    for level in (KUHN_LEVELS if game == "kuhn" else LEDUC_LEVELS):
        key = kuhn_key(*level) if game == "kuhn" else leduc_key(*level)
        rows.append({"game": game, "buckets": list(level), "iterations": iterations,
                     "abstract_infosets": len(infosets(abstract(root, key))),
                     "exploitability": exploitability(root, solve(root, key, iterations))})
    solver = CFRPlus(root)
    solver.iterate(iterations)
    rows.append({"game": game, "buckets": None, "iterations": iterations, "abstract_infosets": len(solver.info),
                 "exploitability": exploitability(root, solver.average_strategy())})
    return rows


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="E0 bottleneck complexity-cost curve (local reference numbers)")
    ap.add_argument("--game", choices=["kuhn", "leduc"], required=True)
    ap.add_argument("--iters", type=int, default=500)
    a = ap.parse_args()
    for r in curve(a.game, a.iters):
        print(json.dumps(r))
