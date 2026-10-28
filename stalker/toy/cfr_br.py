"""CFR-BR for the E0 toy bottlenecks: optimize the bottleneck policy directly against a full-game best response.

`bottleneck.solve` abstracts *both* players and plays the abstract game's equilibrium in the real
game (translation). That can over- or under-state what the bottleneck allows (abstraction
pathologies, Waugh et al. 2009). CFR-BR (Johanson et al. 2012, AAAI "Finding Optimal Abstract
Strategies in Extensive-Form Games") instead updates only the bottlenecked player, by CFR+ on its
merged infosets, while the opponent answers every iterate with an exact best response in the full
game. With perfect recall the average converges to the least exploitable strategy the bottleneck can
express; with imperfect recall there is no such guarantee (docs/research/2026-10-27-abstraction-exploitability.md).

`asymmetric` solves the same target game (bottlenecked player vs an unabstracted opponent, Waugh et
al. 2009 Theorem 3) by plain CFR+ self-play instead of a best-responding opponent; it converges much
faster on the toy games, so the two columns cross-check each other.

Each player is optimized on its own because a profile's exploitability (BR0 + BR1) / 2 splits into a
term per player.
"""
from __future__ import annotations

from itertools import permutations

import numpy as np

from referee.anchors.toy import exploitability, kuhn, leduc
from referee.anchors.toy.game import CHANCE, PLAYER, TERMINAL, Node, _probs, infosets

from . import bottleneck as bn
from .bottleneck import KeyFn
from .cfr import CFRPlus


def best_response(root: Node, strategy: dict, br_player: int) -> dict[str, int]:
    """Exact pure best response of br_player to `strategy`: infoset -> action index.

    Same deepest-first rule as `referee.anchors.toy.best_response_value` (valid because the full game
    has perfect recall), but returns the choices so they can be played against.
    """
    sign = 1.0 if br_player == 0 else -1.0
    weight: dict[int, float] = {}
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
    return choice


class CFRBR:
    """CFR+ (RM+, linear averaging) for `player` on the bottleneck `key`, opponent = full-game BR."""

    def __init__(self, root: Node, key: KeyFn, player: int):
        self.root, self.key, self.player = root, key, player
        own = {i: a for i, (p, a) in infosets(root).items() if p == player}
        self.abstract = {key(i): len(a) for i, a in own.items()}
        self.own = list(own)
        self.regret = {k: np.zeros(n) for k, n in self.abstract.items()}
        self.avg = {k: np.zeros(n) for k, n in self.abstract.items()}
        self.iterations = 0

    def _current(self) -> dict[str, np.ndarray]:
        out = {}
        for k, r in self.regret.items():
            s = r.sum()
            out[k] = r / s if s > 0 else np.full(len(r), 1.0 / len(r))
        return out

    def _lift(self, abstract: dict) -> dict[str, list[float]]:
        return {i: list(abstract[self.key(i)]) for i in self.own}

    def _walk(self, nd: Node, sigma: dict, br: dict, delta: dict, t: int, reach_self: float,
              reach_other: float) -> float:
        """Counterfactual value for `player`; the opponent plays its pure best response `br`."""
        p = self.player
        if nd.kind == TERMINAL:
            return nd.utility if p == 0 else -nd.utility
        if nd.kind == CHANCE:
            return sum(q * self._walk(c, sigma, br, delta, t, reach_self, reach_other * q)
                       for q, c in zip(nd.probs, nd.children))
        if nd.player != p:
            return self._walk(nd.children[br[nd.infoset]], sigma, br, delta, t, reach_self, reach_other)
        k = self.key(nd.infoset)
        s = sigma[k]
        vals = np.array([self._walk(c, sigma, br, delta, t, reach_self * s[i], reach_other)
                         for i, c in enumerate(nd.children)])
        v = float(s @ vals)
        delta[k] += reach_other * (vals - v)
        self.avg[k] += t * reach_self * s
        return v

    def iterate(self, n: int = 1) -> None:
        for _ in range(n):
            self.iterations += 1
            sigma = self._current()
            br = best_response(self.root, self._lift(sigma), 1 - self.player)
            delta = {k: np.zeros(len(s)) for k, s in sigma.items()}
            self._walk(self.root, sigma, br, delta, self.iterations, 1.0, 1.0)
            for k, d in delta.items():
                np.maximum(self.regret[k] + d, 0.0, out=self.regret[k])

    def strategy(self) -> dict[str, list[float]]:
        """Average strategy of `player`, lifted to the full game's infosets."""
        avg = {}
        for k, s in self.avg.items():
            tot = s.sum()
            avg[k] = (s / tot if tot > 0 else np.full(len(s), 1.0 / len(s))).tolist()
        return self._lift(avg)


def solve(root: Node, key: KeyFn, iterations: int) -> dict[str, list[float]]:
    """Both players' CFR-BR strategies inside the bottleneck, as one full-game profile."""
    out: dict[str, list[float]] = {}
    for p in (0, 1):
        s = CFRBR(root, key, p)
        s.iterate(iterations)
        out.update(s.strategy())
    return out


def asymmetric(root: Node, key: KeyFn, iterations: int) -> dict[str, list[float]]:
    """Per player p: CFR+ on the game where only p is bottlenecked; p's average strategy, as one profile."""
    info = infosets(root)
    out: dict[str, list[float]] = {}
    for p in (0, 1):
        own = {i for i, (q, _) in info.items() if q == p}

        def k(i: str, own=own) -> str:
            return key(i) if i in own else i
        solver = CFRPlus(bn.abstract(root, k))
        solver.iterate(iterations)
        out.update({i: s for i, s in bn.lift(root, solver.average_strategy(), k).items() if i in own})
    return out


def perfect_recall(root: Node, key: KeyFn) -> bool:
    """True if every merged infoset is reached by a single sequence of its player's own (merged infoset, action)."""
    seq: dict[str, tuple] = {}

    def walk(n: Node, hist: tuple[tuple, tuple]) -> bool:
        if n.kind == TERMINAL:
            return True
        if n.kind == CHANCE:
            return all(walk(c, hist) for c in n.children)
        k = key(n.infoset)
        if seq.setdefault(k, hist[n.player]) != hist[n.player]:
            return False
        for a, c in zip(n.actions, n.children):
            h = list(hist)
            h[n.player] = hist[n.player] + ((k, a),)
            if not walk(c, (h[0], h[1])):
                return False
        return True
    return walk(root, ((), ()))


def refines(root: Node, fine: KeyFn, coarse: KeyFn) -> bool:
    """True if every infoset merged by `fine` is also merged by `coarse` (fine is nested in coarse)."""
    image: dict[str, str] = {}
    return all(image.setdefault(fine(i), coarse(i)) == coarse(i) for i in infosets(root))


def _partition(root: Node, key: KeyFn) -> frozenset:
    groups: dict[str, set] = {}
    for i in infosets(root):
        groups.setdefault(key(i), set()).add(i)
    return frozenset(frozenset(g) for g in groups.values())


def compare(game: str, iterations: int) -> list[dict]:
    """Exploitability of translation (`bottleneck.solve`), `asymmetric` and CFR-BR per bottleneck size, exact BR."""
    root = {"kuhn": kuhn.game, "leduc": leduc.game}[game]()
    rows = []
    for level in (bn.KUHN_LEVELS if game == "kuhn" else bn.LEDUC_LEVELS):
        key = bn.kuhn_key(*level) if game == "kuhn" else bn.leduc_key(*level)
        rows.append({"game": game, "buckets": list(level), "iterations": iterations,
                     "abstract_infosets": len(infosets(bn.abstract(root, key))),
                     "perfect_recall": perfect_recall(root, key),
                     "translation": exploitability(root, bn.solve(root, key, iterations)),
                     "asymmetric": exploitability(root, asymmetric(root, key, iterations)),
                     "cfr_br": exploitability(root, solve(root, key, iterations))})
    return rows


def monotonicity_warnings(game: str, rows: list[dict], tol: float = 1e-3) -> list[dict]:
    """Strictly nested bottleneck pairs where the finer one is more exploitable (by more than tol).

    Classification follows docs/research/2026-10-27-abstraction-exploitability.md: for the direct methods
    (asymmetric, CFR-BR) with perfect recall on both sides it is a `defect` (convergence is guaranteed),
    otherwise `no_convergence`; for translation it is a `pathology` (allowed, Waugh et al. 2009). None
    fail a test.
    """
    root = {"kuhn": kuhn.game, "leduc": leduc.game}[game]()
    make = bn.kuhn_key if game == "kuhn" else bn.leduc_key
    keys = {tuple(r["buckets"]): make(*r["buckets"]) for r in rows}
    parts = {lv: _partition(root, k) for lv, k in keys.items()}
    by = {tuple(r["buckets"]): r for r in rows}
    out = []
    for fine, coarse in permutations(keys, 2):
        if parts[fine] == parts[coarse] or not refines(root, keys[fine], keys[coarse]):
            continue
        for method in ("translation", "asymmetric", "cfr_br"):
            gap = by[fine][method] - by[coarse][method]
            if gap <= tol:
                continue
            if method == "translation":
                kind = "pathology"
            else:
                kind = "defect" if by[fine]["perfect_recall"] and by[coarse]["perfect_recall"] else "no_convergence"
            out.append({"game": game, "method": method, "fine": list(fine), "coarse": list(coarse),
                        "gap": gap, "kind": kind})
    return out


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="E0: translation vs CFR-BR exploitability per bottleneck (local reference)")
    ap.add_argument("--game", choices=["kuhn", "leduc"], required=True)
    ap.add_argument("--iters", type=int, default=500)
    a = ap.parse_args()
    rows = compare(a.game, a.iters)
    for r in rows:
        print(json.dumps(r))
    for w in monotonicity_warnings(a.game, rows):
        print(json.dumps({"warning": "non_monotone", **w}))
