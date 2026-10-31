"""Heads-up river subgame for range-vector CFR (#393): the public betting tree and the showdown kernels.

A river subgame is a fixed five-card board, both players' ranges over the combos that do not touch the
board (1,081 of 1,326), a pot and an equal stack behind. Player 0 (out of position) acts first. The
betting tree is public: it does not depend on the hole cards, so one tree serves every combo and CFR
works on (node, combo) vectors instead of sampled deals.

Terminal values are computed for all combos at once without the 1,081 x 1,081 hand-vs-hand matrix:
combos are sorted by strength once, the opponent's reach is summed cumulatively (wins below, losses
above), and card removal is subtracted with the same sums taken per card (inclusion-exclusion: the only
combo sharing both cards with mine is mine, a tie). That is O(n) per evaluation after one O(n log n)
sort per board, and it is the form that batches on a GPU. `dense_values` keeps the matrix version as
the test reference.

Amounts are in pots: the pot at the start of the river is 1.0, half from each player.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from stalker.core.cards import COMBOS
from stalker.core.fast_eval import evaluate_batch

ALL_COMBOS = np.array(COMBOS, dtype=np.int64)
# Real-play river sizes (#382, stalker/e3/game.py REAL_BET / REAL_RAISE): bets in pots, raises x the bet.
REAL_BETS = (0.2, 0.33, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)
REAL_RAISES = (2.5, 3.0, 4.0, 5.0, 7.0, 10.0)


class Showdown:
    """Strength order and card groups of one board's combos, for O(n) terminal values."""

    def __init__(self, board: tuple[int, ...]):
        if len(board) != 5 or len(set(board)) != 5:
            raise ValueError(f"a river board has five distinct cards, got {board}")
        self.board = tuple(int(c) for c in board)
        ok = ~np.isin(ALL_COMBOS, self.board).any(axis=1)
        self.combo_ids = np.flatnonzero(ok)            # positions in the 1,326 list
        self.cards = ALL_COMBOS[ok]                    # (n, 2)
        self.n = n = len(self.cards)
        hands = np.concatenate([self.cards, np.broadcast_to(np.array(self.board), (n, 5))], axis=1)
        _, rank = np.unique(evaluate_batch(hands), return_inverse=True)
        self.rank = rank = rank.astype(np.int64).ravel()
        u = int(rank.max()) + 2
        self.order = np.argsort(rank, kind="stable")
        rs = rank[self.order]
        self.lo, self.hi = np.searchsorted(rs, rank, "left"), np.searchsorted(rs, rank, "right")
        # Per (card, combo) pair, sorted by card then strength: the same sums restricted to one card.
        pc = np.concatenate([self.cards[:, 0], self.cards[:, 1]])
        self.pair_combo = np.concatenate([np.arange(n), np.arange(n)])
        comp = pc * u + rank[self.pair_combo]
        self.pair_order = np.argsort(comp, kind="stable")
        cs = comp[self.pair_order]
        self.plo, self.phi = np.searchsorted(cs, comp, "left"), np.searchsorted(cs, comp, "right")
        self.gs, self.ge = np.searchsorted(cs, pc * u, "left"), np.searchsorted(cs, (pc + 1) * u, "left")

    def card_mass(self, r: np.ndarray) -> np.ndarray:
        """Mass of `r` on combos that share no card with each combo (the opponent's live mass)."""
        per_card = np.bincount(self.cards[:, 0], r, 52) + np.bincount(self.cards[:, 1], r, 52)
        return r.sum() - per_card[self.cards[:, 0]] - per_card[self.cards[:, 1]] + r

    def less_greater(self, r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Opponent mass that each combo beats, and that beats it, card removal included."""
        n = self.n
        cum = np.concatenate([[0.0], np.cumsum(r[self.order])])
        less, greater = cum[self.lo], cum[-1] - cum[self.hi]
        pcum = np.concatenate([[0.0], np.cumsum(r[self.pair_combo[self.pair_order]])])
        pl = pcum[self.plo] - pcum[self.gs]
        pg = pcum[self.ge] - pcum[self.phi]
        return less - pl[:n] - pl[n:], greater - pg[:n] - pg[n:]

    def equity(self, r: np.ndarray) -> np.ndarray:
        """Showdown equity (win + half a tie) of every combo against the range `r` (0.5 where it is empty)."""
        less, greater = self.less_greater(r)
        live = self.card_mass(r)
        ties = live - less - greater
        with np.errstate(invalid="ignore", divide="ignore"):
            eq = (less + 0.5 * ties) / live
        return np.clip(np.where(live > 1e-12, eq, 0.5), 0.0, 1.0)   # cumulative sums leave ~1e-16 noise

    def dense_values(self, r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(wins minus losses, live mass) from the full matrix: the O(n^2) reference for the tests."""
        a, b = self.cards[:, 0], self.cards[:, 1]
        valid = ~((a[:, None] == a[None, :]) | (a[:, None] == b[None, :]) | (b[:, None] == a[None, :])
                  | (b[:, None] == b[None, :]))
        sign = np.sign(self.rank[:, None] - self.rank[None, :]) * valid
        return sign @ r, valid.astype(float) @ r


@dataclass
class Node:
    id: int
    kind: str                       # "act", "fold", "show"
    player: int = -1                # to act ("act") or who folded ("fold")
    contrib: tuple[float, float] = (0.5, 0.5)
    raises: int = 0                 # bets and raises so far on the street
    to_call: float = 0.0
    labels: tuple[str, ...] = ()
    children: list["Node"] = field(default_factory=list)


@dataclass
class RiverGame:
    board: tuple[int, ...]
    stack: float = 2.0                          # behind, in pots, the same for both
    bets: tuple[float, ...] = (0.5, 1.0)        # pot fractions when nothing is to call
    raises: tuple[float, ...] = (3.0,)          # x the current bet when facing one
    raise_cap: int = 2                          # bets + raises per street; at the cap only fold/call
    allin: bool = True
    ranges: tuple[np.ndarray, np.ndarray] | None = None   # over the board's combos; None = uniform

    def __post_init__(self):
        self.sd = Showdown(self.board)
        n = self.sd.n
        if self.ranges is None:
            self.init = (np.ones(n), np.ones(n))
        else:
            self.init = tuple(np.asarray(r, dtype=float) for r in self.ranges)
            if any(r.shape != (n,) for r in self.init):
                raise ValueError(f"ranges must have the board's {n} combos")
        self.nodes: list[Node] = []
        self.root = self._build(0, (0.5, 0.5), 0, False)

    def _new(self, **kw) -> Node:
        node = Node(id=len(self.nodes), **kw)
        self.nodes.append(node)
        return node

    def _build(self, p: int, c: tuple[float, float], raises: int, checked: bool) -> Node:
        most = 0.5 + self.stack                        # the most a player can have in
        to_call = c[1 - p] - c[p]
        node = self._new(kind="act", player=p, contrib=c, raises=raises, to_call=to_call)
        pot = c[0] + c[1]
        kids: list[tuple[str, Node]] = []

        def put(to: float) -> tuple[float, float]:
            out = list(c)
            out[p] = to
            return out[0], out[1]

        if to_call > 1e-12:
            kids.append(("f", self._new(kind="fold", player=p, contrib=c)))
            kids.append(("c", self._new(kind="show", contrib=put(c[1 - p]))))
            if c[1 - p] < most - 1e-12 and raises < self.raise_cap:
                seen: list[float] = []
                street_bet = c[1 - p] - 0.5
                for x in self.raises:
                    to = 0.5 + max(x * street_bet, street_bet + to_call)     # at least a min-raise
                    if to < most - 1e-9 and all(abs(to - t) > 1e-9 for t in seen):
                        seen.append(to)
                        kids.append((f"r{x:g}", self._build(1 - p, put(to), raises + 1, False)))
                if self.allin:
                    kids.append(("a", self._build(1 - p, put(most), raises + 1, False)))
        else:
            nxt = self._new(kind="show", contrib=c) if checked else self._build(1 - p, c, raises, True)
            kids.append(("k", nxt))
            seen = []
            for f in self.bets:
                to = c[p] + f * pot
                if to < most - 1e-9 and all(abs(to - t) > 1e-9 for t in seen):
                    seen.append(to)
                    kids.append((f"b{round(100 * f)}", self._build(1 - p, put(to), raises + 1, False)))
            if self.allin and c[p] < most - 1e-12:
                kids.append(("a", self._build(1 - p, put(most), raises + 1, False)))
        node.labels = tuple(a for a, _ in kids)
        node.children = [k for _, k in kids]
        return node

    def decision_nodes(self) -> list[Node]:
        return [nd for nd in self.nodes if nd.kind == "act"]

    def equity(self, node: Node, r_opp: np.ndarray) -> np.ndarray:
        """Equity of the player to act at `node` against `r_opp`: one board, so the node does not matter."""
        return self.sd.equity(r_opp)

    def own_mass(self, node: Node, q: int) -> np.ndarray:
        """Chance weight of player q's combos: the opponent's starting live mass (the same at every node)."""
        if not hasattr(self, "_own_mass"):
            self._own_mass = [self.sd.card_mass(self.init[1]), self.sd.card_mass(self.init[0])]
        return self._own_mass[q]

    def terminal_value(self, node: Node, p: int, r_opp: np.ndarray) -> np.ndarray:
        """Counterfactual value of every combo of player p at a terminal (weighted by the opponent's reach)."""
        if node.kind == "fold":
            live = self.sd.card_mass(r_opp)
            return live * (-node.contrib[p] if node.player == p else node.contrib[1 - p])
        less, greater = self.sd.less_greater(r_opp)
        return node.contrib[p] * (less - greater)    # a call: both contributions are equal
