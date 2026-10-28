"""Two-player zero-sum game trees and exact best response.

A strategy is `{infoset: probs}` with probs aligned to that infoset's `actions`. Infosets missing
from a strategy play uniformly, so a partial strategy is still a complete policy.
Utilities are for player 0; player 1 receives the negation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

CHANCE, PLAYER, TERMINAL = "chance", "player", "terminal"


@dataclass(eq=False)
class Node:
    kind: str
    player: int = -1                     # acting player (PLAYER nodes)
    infoset: str = ""                    # what the acting player knows
    actions: tuple[str, ...] = ()
    children: list["Node"] = field(default_factory=list)
    probs: tuple[float, ...] = ()        # CHANCE nodes
    utility: float = 0.0                 # TERMINAL nodes, for player 0
    depth: int = 0


def finalize(root: Node) -> Node:
    """Set depths and check the tree; call once after building."""
    seen: dict[str, tuple[int, tuple[str, ...], int]] = {}
    stack = [(root, 0)]
    while stack:
        n, d = stack.pop()
        n.depth = d
        if n.kind == CHANCE:
            if len(n.probs) != len(n.children) or abs(sum(n.probs) - 1) > 1e-12:
                raise ValueError(f"chance node at depth {d}: probs must match children and sum to 1")
        elif n.kind == PLAYER:
            if len(n.actions) != len(n.children) or not n.actions:
                raise ValueError(f"infoset {n.infoset!r}: actions must match children")
            key = (n.player, n.actions, d)
            if seen.setdefault(n.infoset, key) != key:
                raise ValueError(f"infoset {n.infoset!r} mixes player/actions/depth; keys must encode them")
        stack.extend((c, d + 1) for c in n.children)
    return root


def infosets(root: Node) -> dict[str, tuple[int, tuple[str, ...]]]:
    """infoset -> (player, actions)."""
    out: dict[str, tuple[int, tuple[str, ...]]] = {}
    stack = [root]
    while stack:
        n = stack.pop()
        if n.kind == PLAYER:
            out[n.infoset] = (n.player, n.actions)
        stack.extend(n.children)
    return out


def _probs(strategy: dict, n: Node) -> np.ndarray:
    p = strategy.get(n.infoset)
    if p is None:
        return np.full(len(n.actions), 1.0 / len(n.actions))
    p = np.asarray(p, dtype=float)
    if p.shape != (len(n.actions),) or (p < -1e-12).any() or abs(p.sum() - 1) > 1e-9:
        raise ValueError(f"strategy at {n.infoset!r} must be {len(n.actions)} probabilities summing to 1")
    return p


def expected_value(root: Node, strategy: dict) -> float:
    """Player 0's expected utility when both players follow `strategy`."""
    def v(n: Node) -> float:
        if n.kind == TERMINAL:
            return n.utility
        w = n.probs if n.kind == CHANCE else _probs(strategy, n)
        return sum(p * v(c) for p, c in zip(w, n.children) if p > 0)
    return v(root)


def best_response_value(root: Node, strategy: dict, br_player: int) -> float:
    """Exact value (for br_player) of the best response to the other player's part of `strategy`.

    Infosets of br_player are decided deepest first: with perfect recall every infoset below a
    history is deeper, so by the time an infoset is decided all values under it are final.
    """
    sign = 1.0 if br_player == 0 else -1.0
    weight: dict[int, float] = {}          # chance x opponent reach, per node id
    members: dict[str, list[Node]] = {}
    stack = [(root, 1.0)]
    while stack:
        n, w = stack.pop()
        weight[id(n)] = w
        if n.kind == TERMINAL:
            continue
        if n.kind == PLAYER and n.player == br_player:
            members.setdefault(n.infoset, []).append(n)
            stack.extend((c, w) for c in n.children)
        else:
            ps = n.probs if n.kind == CHANCE else _probs(strategy, n)
            stack.extend((c, w * p) for c, p in zip(n.children, ps))

    choice: dict[str, int] = {}
    memo: dict[int, float] = {}

    def v(n: Node) -> float:
        k = id(n)
        if k in memo:
            return memo[k]
        if n.kind == TERMINAL:
            r = sign * n.utility
        elif n.kind == PLAYER and n.player == br_player:
            r = v(n.children[choice[n.infoset]])
        else:
            ps = n.probs if n.kind == CHANCE else _probs(strategy, n)
            r = sum(p * v(c) for p, c in zip(ps, n.children) if p > 0)
        memo[k] = r
        return r

    for info in sorted(members, key=lambda i: -members[i][0].depth):
        nodes = members[info]
        scores = [sum(weight[id(h)] * v(h.children[a]) for h in nodes) for a in range(len(nodes[0].actions))]
        choice[info] = int(np.argmax(scores))
    return v(root)


def exploitability(root: Node, strategy: dict) -> float:
    """Mean best-response gain: (BR0 + BR1) / 2. Zero exactly at a Nash equilibrium."""
    return (best_response_value(root, strategy, 0) + best_response_value(root, strategy, 1)) / 2
