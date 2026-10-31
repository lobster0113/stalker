"""Leduc hold'em as a public-tree game for `solver.VectorCFR` (#411): range-dependent TP keys with a chance node.

The rules and payoffs are those of referee/anchors/toy/leduc.py (tests check the equilibrium value). A
private state is a rank (J, Q, K), so a range is a 3-vector; the public card is a chance node between the
rounds. Act and terminal nodes carry the joint chance matrix C[x, y] of (my rank, the other rank, board so
far), so terminal values are C x payoff contracted with the opponent's reach, as `toy.leduc_public` does.

Unlike the river, the starting ranges of round 2 are the round-1 strategy: here "initial" ranges (the
deal) are far from the ranges a round-2 node is reached with, which is the full-game form of the question
#411 asks. Seeds give each player a different prior over the ranks (a subgame entered with uneven ranges).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from referee.anchors.toy import leduc as L

POT = 2.0          # the antes: amounts in "% pot" are per this starting pot


@dataclass(eq=False)
class LNode:
    id: int
    kind: str                                      # "act", "chance", "term"
    player: int = -1
    children: list["LNode"] = field(default_factory=list)
    chance: np.ndarray | None = None               # (3, 3) P(rank0, rank1, board so far)
    value: np.ndarray | None = None                # "term": chance x player 0's payoff
    win0: np.ndarray | None = None                 # "act": P(player 0 wins) + half a tie, per (rank0, rank1)
    labels: tuple[str, ...] = ()


class _Deal:
    """The `sd` part of the river interface the solver and best response use."""

    def __init__(self, c1: np.ndarray):
        self.n = 3
        self.c1 = c1

    def card_mass(self, r: np.ndarray) -> np.ndarray:
        return self.c1 @ r        # symmetric: the same for either seat


class LeducGame:
    pot = POT

    def __init__(self, priors: tuple[np.ndarray, np.ndarray] | None = None):
        cnt = np.array([L.DECK.count(r) for r in range(3)], dtype=float)
        ix = np.arange(3)
        c1 = cnt[:, None] / 6 * (cnt[None, :] - np.eye(3)) / 5
        c2 = [c1 * np.maximum(cnt[b] - (ix[:, None] == b) - (ix[None, :] == b), 0) / 4 for b in range(3)]
        w = [np.array([[(L._showdown((x, y), b) + 1) / 2 for y in range(3)] for x in range(3)]) for b in range(3)]
        sign = [2 * m - 1 for m in w]
        with np.errstate(invalid="ignore", divide="ignore"):
            pre = np.where(c1 > 0, sum(c2[b] * w[b] for b in range(3)) / c1, 0.5)
        self.sd = _Deal(c1)
        self.init = (np.ones(3), np.ones(3)) if priors is None else tuple(np.asarray(p, dtype=float) for p in priors)
        self.nodes: list[LNode] = []

        def new(**kw) -> LNode:
            nd = LNode(id=len(self.nodes), **kw)
            self.nodes.append(nd)
            return nd

        def node(r1: str, r2: str | None, b: int | None) -> LNode:
            rnd = 0 if r2 is None else 1
            h = r1 if rnd == 0 else r2
            start = 1 if rnd == 0 else L._contrib(r1, L.BET[0], 1)[0]
            c = c1 if b is None else c2[b]
            if L._round_over(h):
                put = L._contrib(h, L.BET[rnd], start)
                if h[-1] == "f":
                    return new(kind="term", chance=c, value=c * (-put[0] if (len(h) - 1) % 2 == 0 else put[1]))
                if rnd == 0:
                    ch = new(kind="chance")
                    ch.children = [node(r1, "", d) for d in range(3)]
                    return ch
                return new(kind="term", chance=c, value=c * sign[b] * put[0])
            acts = L._actions(h)
            nd = new(kind="act", player=len(h) % 2, chance=c, win0=pre if b is None else w[b], labels=acts)
            nd.children = [node(r1 + a, None, None) if rnd == 0 else node(r1, r2 + a, b) for a in acts]
            return nd

        self.root = node("", None, None)

    def decision_nodes(self) -> list[LNode]:
        return [nd for nd in self.nodes if nd.kind == "act"]

    def terminal_value(self, node: LNode, p: int, r_opp: np.ndarray) -> np.ndarray:
        return node.value @ r_opp if p == 0 else -(node.value.T @ r_opp)

    def own_mass(self, node: LNode, q: int) -> np.ndarray:
        """Chance weight of player q's ranks at `node` (deck, board and the opponent's prior)."""
        return node.chance @ self.init[1] if q == 0 else node.chance.T @ self.init[0]

    def equity(self, node: LNode, r_opp: np.ndarray) -> np.ndarray:
        """Equity of the player to act against `r_opp` (round 1: over the board still to come)."""
        c, w = (node.chance, node.win0) if node.player == 0 else (node.chance.T, 1 - node.win0.T)
        den = c @ r_opp
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(den > 1e-12, ((c * w) @ r_opp) / den, 0.5)


def random_priors(seed: int) -> tuple[np.ndarray, np.ndarray] | None:
    """Seed 0: the plain deal. Otherwise each player's ranks weighted 0.2-1 (paired across arms)."""
    if seed == 0:
        return None
    rng = np.random.default_rng(seed)
    return rng.uniform(0.2, 1.0, 3), rng.uniform(0.2, 1.0, 3)
