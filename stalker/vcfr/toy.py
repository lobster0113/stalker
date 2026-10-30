"""Oracle for the TP-merged regret update on Kuhn and Leduc (#414).

The question: when infosets are merged into one key (a TP key), is the scatter-add of regrets over the
key the update of the intended abstract game, and does the E3 sampler (stalker/e3/mccfr.py) make that
update in expectation? Three solvers share one abstraction, a key function from infoset to key (as in
stalker/toy/bottleneck.py), on the games of referee/anchors/toy:

(a) `exact_update` / `ExactCFR`: the full game tree, every history weighted exactly.
(b) `VectorCFR`: the public tree, each player's private state a vector, regrets scatter-added from
    private states into keys with the weight w(I) explicit (`scatter_regret`).
(c) `E3Sampler`: one sampled deal per update, every action of the traverser explored and every other
    player's action sampled from the current strategy, as stalker/e3/mccfr.py does. Off-policy sampling
    (`explore`, `uniform_chance`) exists only to test the sampling correction, which is 1 in E3.

The intended update of one pass with traverser p, every strategy held fixed for the pass
(docs/research/2026-10-range-vector-tp-cfr.md section 8):

    R[k, a] += sum over h in key k, p to act:       pi_c(h) pi_-p(h) (u_p(h a) - u_p(h))
    S[k, a] += sum over h in key k, i != p to act:  pi_c(h) pi_i(h) sigma(k, a)

S is accumulated in the other players' passes, as E3 does.

    python -m stalker.vcfr.toy        # noise of the sampled update against samples (reference numbers)
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import permutations

import numpy as np

from referee.anchors.toy import kuhn, leduc
from referee.anchors.toy.game import CHANCE, PLAYER, TERMINAL, Node, finalize

KeyFn = Callable[[str], str]
Table = dict[str, np.ndarray]


def identity(infoset: str) -> str:
    return infoset


def payoff(n: Node, p: int) -> float:
    """Utility of player p at a terminal: two-player trees store player 0's, N-player trees a tuple."""
    u = n.utility
    return float(u[p]) if isinstance(u, tuple) else (u if p == 0 else -u)


def keys(root: Node, key: KeyFn = identity) -> dict[str, tuple[int, int]]:
    """key -> (player, number of actions)."""
    out: dict[str, tuple[int, int]] = {}
    stack = [root]
    while stack:
        n = stack.pop()
        if n.kind == PLAYER:
            out[key(n.infoset)] = (n.player, len(n.actions))
        stack.extend(n.children)
    return out


# Merged infosets can cancel a regret to exactly zero; rounding leaves +-1e-17 there, which regret
# matching would turn into a pure strategy, and the two solvers' different summation orders would split.
EPS = 1e-12


def regret_match(r: np.ndarray) -> np.ndarray:
    pos = np.where(r > EPS, r, 0.0)
    t = pos.sum()
    return pos / t if t > 0 else np.full(len(r), 1.0 / len(r))


def random_sigma(root: Node, key: KeyFn, rng: np.random.Generator) -> Table:
    return {k: rng.dirichlet(np.ones(a)) for k, (_, a) in sorted(keys(root, key).items())}


def _acc(t: Table, k: str, x: np.ndarray) -> None:
    t[k] = t[k] + x if k in t else np.array(x, dtype=float)


def exact_update(root: Node, key: KeyFn, sigma: Table, p: int, n_players: int = 2,
                 avg_reach: str = "own") -> tuple[Table, Table]:
    """(a) The intended update of one pass with traverser p (module docstring), summed over histories.

    avg_reach="e3" weights the average-strategy increment by pi_c pi_-p instead of pi_c pi_i: what the
    E3 sampler makes in expectation. The two are equal with two players and differ with more."""
    if avg_reach not in ("own", "e3"):
        raise ValueError(f"avg_reach={avg_reach!r}; use 'own' or 'e3'")
    reg: Table = {}
    avg: Table = {}

    def walk(n: Node, pi: np.ndarray) -> float:      # pi[m]: reach of player m; pi[-1]: chance
        if n.kind == TERMINAL:
            return payoff(n, p)
        if n.kind == CHANCE:
            out = 0.0
            for q, c in zip(n.probs, n.children):
                nxt = pi.copy()
                nxt[-1] *= q
                out += q * walk(c, nxt)
            return out
        k, q = key(n.infoset), n.player
        s = sigma[k]
        vals = np.empty(len(n.children))
        for a, c in enumerate(n.children):
            nxt = pi.copy()
            nxt[q] *= s[a]
            vals[a] = walk(c, nxt)
        v = float(s @ vals)
        others = pi[-1] * np.prod(np.delete(pi[:-1], p))
        if q == p:
            _acc(reg, k, others * (vals - v))
        else:
            _acc(avg, k, (pi[-1] * pi[q] if avg_reach == "own" else others) * s)
        return v

    walk(root, np.ones(n_players + 1))
    return reg, avg


class ExactCFR:
    """(a) CFR+ on the full tree with merged keys: alternating passes with one frozen strategy each, the
    regret floor, linear averaging, and player i's average accumulated in the other player's pass (E3)."""

    def __init__(self, root: Node, key: KeyFn = identity):
        self.root, self.key = root, key
        self.info = keys(root, key)
        self.regret = {k: np.zeros(a) for k, (_, a) in self.info.items()}
        self.avg = {k: np.zeros(a) for k, (_, a) in self.info.items()}
        self.t = 0

    def sigma(self) -> Table:
        return {k: regret_match(r) for k, r in self.regret.items()}

    def iterate(self, n: int = 1) -> None:
        for _ in range(n):
            self.t += 1
            for p in (0, 1):
                reg, avg = exact_update(self.root, self.key, self.sigma(), p)
                for k, d in reg.items():
                    np.maximum(self.regret[k] + d, 0.0, out=self.regret[k])
                for k, s in avg.items():
                    self.avg[k] += self.t * s

    def average_strategy(self) -> dict[str, list[float]]:
        return {k: (s / s.sum() if s.sum() > 0 else np.full(len(s), 1 / len(s))).tolist() for k, s in self.avg.items()}


# ---- (b) the public tree in vector form ----

@dataclass(eq=False)
class PNode:
    kind: str                                    # "act", "chance", "term"
    player: int = -1
    infosets: tuple[str, ...] = ()               # "act": the acting player's infoset per private state
    children: list["PNode"] = field(default_factory=list)
    chance: np.ndarray | None = None             # "act": (X0, X1) probability of the deal and public cards so far
    value: np.ndarray | None = None              # "term": chance x u_0 per (x0, x1)


def kuhn_public() -> PNode:
    """Kuhn on its public tree: private state = own card; same infosets and payoffs as referee kuhn."""
    c = (1 - np.eye(3)) / 6
    sign = np.sign(np.arange(3)[:, None] - np.arange(3)[None, :])

    def node(h: str) -> PNode:
        if h in ("kk", "bc", "kbc"):
            return PNode("term", value=c * sign * (1 if h == "kk" else 2))
        if h in ("bf", "kbf"):
            return PNode("term", value=c * (1.0 if h == "bf" else -1.0))
        acts = ("c", "f") if h.endswith("b") else ("k", "b")
        return PNode("act", player=len(h) % 2, infosets=tuple(f"{x}:{h}" for x in kuhn.CARDS), chance=c,
                     children=[node(h + a) for a in acts])
    return node("")


def leduc_public() -> PNode:
    """Leduc on its public tree: private state = own rank, the board card a public chance node."""
    cnt = np.array([leduc.DECK.count(r) for r in range(3)], dtype=float)
    ix = np.arange(3)
    c1 = cnt[:, None] / 6 * (cnt[None, :] - np.eye(3)) / 5
    c2 = [c1 * np.maximum(cnt[b] - (ix[:, None] == b) - (ix[None, :] == b), 0) / 4 for b in range(3)]
    show = [np.array([[leduc._showdown((x, y), b) for y in range(3)] for x in range(3)], dtype=float) for b in range(3)]

    def node(r1: str, r2: str | None, b: int | None) -> PNode:
        rnd = 0 if r2 is None else 1
        h = r1 if rnd == 0 else r2
        start = 1 if rnd == 0 else leduc._contrib(r1, leduc.BET[0], 1)[0]
        c = c1 if b is None else c2[b]
        if leduc._round_over(h):
            put = leduc._contrib(h, leduc.BET[rnd], start)
            if h[-1] == "f":
                return PNode("term", value=c * (-put[0] if (len(h) - 1) % 2 == 0 else put[1]))
            if rnd == 0:
                return PNode("chance", children=[node(r1, "", d) for d in range(3)])
            return PNode("term", value=c * show[b] * put[0])
        seen = "" if b is None else leduc.RANKS[b]
        hist = r1 + ("" if r2 is None else f"/{r2}")
        kids = [node(r1 + a, None, None) if rnd == 0 else node(r1, r2 + a, b) for a in leduc._actions(h)]
        return PNode("act", player=len(h) % 2, chance=c, children=kids,
                     infosets=tuple(f"{leduc.RANKS[x]}{seen}:{hist}" for x in range(3)))
    return node("", None, None)


def scatter_regret(table: np.ndarray, rows: np.ndarray, w: np.ndarray, d: np.ndarray) -> None:
    """R[key(I)] += w(I) d(I): counterfactual reach times the conditional regret, summed over a key's infosets."""
    np.add.at(table, rows, w[:, None] * d)


class VectorCFR:
    """(b) The same CFR+ schedule as `ExactCFR` on the public tree, private states as vectors."""

    def __init__(self, root: PNode, key: KeyFn = identity):
        self.root, self.key = root, key
        self.ids: dict[str, int] = {}
        self.rows: dict[int, np.ndarray] = {}
        nact: dict[int, int] = {}
        stack = [root]
        while stack:
            n = stack.pop()
            if n.kind == "act":
                r = [self.ids.setdefault(key(i), len(self.ids)) for i in n.infosets]
                self.rows[id(n)] = np.array(r)
                nact.update((x, len(n.children)) for x in r)
            stack.extend(n.children)
        self.nact = np.array([nact[i] for i in range(len(self.ids))])
        width = int(self.nact.max())
        self.mask = np.arange(width)[None, :] < self.nact[:, None]
        self.regret = np.zeros((len(self.ids), width))
        self.avg = np.zeros_like(self.regret)
        self.t = 0

    def sigma(self) -> np.ndarray:
        pos = np.where(self.regret > EPS, self.regret, 0.0) * self.mask
        tot = pos.sum(axis=1, keepdims=True)
        return np.where(tot > 0, pos / np.where(tot > 0, tot, 1.0), self.mask / self.nact[:, None])

    def from_table(self, t: Table) -> np.ndarray:
        out = np.zeros_like(self.regret)
        for k, i in self.ids.items():
            out[i, :self.nact[i]] = t[k]
        return out

    def to_table(self, x: np.ndarray) -> Table:
        return {k: x[i, :self.nact[i]].copy() for k, i in self.ids.items()}

    def update(self, p: int, sig: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """One pass with traverser p under the frozen strategy `sig`: (regret, average) increments."""
        d_reg, d_avg = np.zeros_like(self.regret), np.zeros_like(self.regret)

        def walk(n: PNode, r: list[np.ndarray]) -> np.ndarray:
            if n.kind == "term":
                return n.value @ r[1] if p == 0 else -(n.value.T @ r[0])
            if n.kind == "chance":
                return sum(walk(c, r) for c in n.children)
            q, rows, m = n.player, self.rows[id(n)], len(n.children)
            s = sig[rows, :m]
            if q == p:
                vals = np.stack([walk(c, r) for c in n.children], axis=1)
                v = (s * vals).sum(axis=1)
                w = n.chance @ r[1] if p == 0 else n.chance.T @ r[0]      # counterfactual reach per infoset
                d = np.divide(vals - v[:, None], w[:, None], out=np.zeros_like(vals), where=w[:, None] > 0)
                scatter_regret(d_reg[:, :m], rows, w, d)
                return v
            np.add.at(d_avg[:, :m], rows, (n.chance.sum(axis=1 - q) * r[q])[:, None] * s)
            out = 0.0
            for a, c in enumerate(n.children):
                rr = list(r)
                rr[q] = r[q] * s[:, a]
                out = out + walk(c, rr)
            return out

        walk(self.root, [np.ones(3), np.ones(3)])
        return d_reg, d_avg

    def iterate(self, n: int = 1) -> None:
        for _ in range(n):
            self.t += 1
            for p in (0, 1):
                d_reg, d_avg = self.update(p, self.sigma())
                np.maximum(self.regret + d_reg, 0.0, out=self.regret)
                self.avg += self.t * d_avg

    def average_strategy(self) -> dict[str, list[float]]:
        return {k: (s / s.sum() if s.sum() > 0 else np.full(len(s), 1 / len(s))).tolist()
                for k, s in self.to_table(self.avg).items()}


# ---- (c) the E3 sampler ----

class E3Sampler:
    """(c) One sampled update with traverser p, as stalker/e3/mccfr.py `_walk` does with the strategy frozen.

    E3 samples chance and the other players on policy, so the correction pi/q is 1 and its update is
    `R[k] += vals - v` and `S[k] += sigma`. `explore` (mixing the sampling with uniform) and
    `uniform_chance` sample off policy; `correct=False` then drops the correction (a mutation)."""

    def __init__(self, root: Node, key: KeyFn = identity, explore: float = 0.0, uniform_chance: bool = False,
                 correct: bool = True):
        self.root, self.key = root, key
        self.explore, self.uniform_chance, self.correct = explore, uniform_chance, correct

    def sample(self, sigma: Table, p: int, rng: np.random.Generator) -> tuple[Table, Table]:
        reg: Table = {}
        avg: Table = {}

        def draw(probs: np.ndarray, q: np.ndarray) -> tuple[int, float]:
            i = int(rng.choice(len(q), p=q))
            return i, (probs[i] / q[i] if self.correct else 1.0)

        def walk(n: Node, w: float) -> float:    # w: correction pi/q of the sampled edges above n
            if n.kind == TERMINAL:
                return payoff(n, p)
            probs = np.asarray(n.probs) if n.kind == CHANCE else sigma[self.key(n.infoset)]
            if n.kind == CHANCE:
                q = np.full(len(probs), 1 / len(probs)) if self.uniform_chance else probs
            elif n.player == p:
                vals = np.array([walk(c, w) for c in n.children])
                v = float(probs @ vals)
                _acc(reg, self.key(n.infoset), w * (vals - v))
                return v
            else:
                _acc(avg, self.key(n.infoset), w * probs)
                q = (1 - self.explore) * probs + self.explore / len(probs)
            i, ratio = draw(probs, q)
            return ratio * walk(n.children[i], w * ratio)

        walk(self.root, 1.0)
        return reg, avg


def flat(info: dict[str, tuple[int, int]], parts: list[tuple[Table, Table]]) -> np.ndarray:
    """Every (key, action) of the regret and average increments of several passes, as one vector."""
    out = []
    for reg, avg in parts:
        for t in (reg, avg):
            out += [t.get(k, np.zeros(a)) for k, (_, a) in sorted(info.items())]
    return np.concatenate(out)


def noise_curve(root: Node, key: KeyFn, ns: tuple[int, ...], seed: int = 0, n_players: int = 2,
                avg_reach: str = "own", **sampler) -> list[dict]:
    """Relative L2 error of the mean of n sampled updates (each traverser once per sample) against the
    exact expected update, at each n in `ns` along one seeded stream. Unbiased: error x sqrt(n) stays flat."""
    rng = np.random.default_rng(seed)
    info = keys(root, key)
    sigma = random_sigma(root, key, rng)
    players = range(n_players)
    target = flat(info, [exact_update(root, key, sigma, p, n_players, avg_reach) for p in players])
    sampler_ = E3Sampler(root, key, **sampler)
    total = np.zeros_like(target)
    out, done = [], 0
    for n in sorted(ns):
        for _ in range(n - done):
            total += flat(info, [sampler_.sample(sigma, p, rng) for p in players])
        done = n
        err = float(np.linalg.norm(total / n - target) / np.linalg.norm(target))
        out.append({"samples": n, "rel_err": round(err, 5), "rel_err_x_sqrt_n": round(err * float(np.sqrt(n)), 3)})
    return out


def kuhn3() -> Node:
    """Three-player Kuhn poker (J<Q<K<A, ante 1, one bet of 1, players 0-1-2 in turn), utilities per player.

    Only here to show the N-player average-strategy weight of the E3 sampler; nothing trains on it."""
    cards = "JQKA"

    def node(deal: tuple[int, ...], h: str) -> Node:
        bettor = h.find("b")
        resp = "" if bettor < 0 else h[bettor + 1:]
        if (bettor < 0 and len(h) == 3) or len(resp) == 2:
            put = [1.0] * 3
            live = [0, 1, 2]
            if bettor >= 0:
                put[bettor] += 1
                live = [bettor]
                for i, a in enumerate(resp):
                    m = (bettor + 1 + i) % 3
                    if a == "c":
                        put[m] += 1
                        live.append(m)
            win = max(live, key=lambda m: deal[m])
            return Node(TERMINAL, utility=tuple((sum(put) if m == win else 0.0) - put[m] for m in range(3)))
        p = len(h) if bettor < 0 else (bettor + 1 + len(resp)) % 3
        acts = ("k", "b") if bettor < 0 else ("c", "f")
        return Node(PLAYER, player=p, infoset=f"{cards[deal[p]]}:{h}", actions=acts,
                    children=[node(deal, h + a) for a in acts])

    deals = list(permutations(range(4), 3))
    return finalize(Node(CHANCE, children=[node(d, "") for d in deals], probs=(1 / len(deals),) * len(deals)))


def main(argv=None) -> int:
    from stalker.toy import bottleneck as b
    ns = (100, 400, 1600, 6400)
    rows = []
    for game, key_name, key in (("kuhn", "kuhn_key(2)", b.kuhn_key(2)), ("leduc", "leduc_key(3,1)", b.leduc_key(3, 1))):
        root = (kuhn if game == "kuhn" else leduc).game()
        for name, kw in (("e3", {}), ("off-policy corrected", {"explore": 0.5, "uniform_chance": True}),
                         ("off-policy uncorrected", {"explore": 0.5, "uniform_chance": True, "correct": False})):
            rows.append({"game": game, "key": key_name, "sampler": name, "curve": noise_curve(root, key, ns, 1, **kw)})
    root = kuhn3()
    for reach in ("e3", "own"):
        rows.append({"game": "kuhn3", "key": "identity", "sampler": "e3", "target_avg_reach": reach,
                     "curve": noise_curve(root, identity, ns, 1, n_players=3, avg_reach=reach)})
    print("\n".join(json.dumps({"note": "local reference numbers, not CI", **r}) for r in rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
