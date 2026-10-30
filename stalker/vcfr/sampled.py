"""The heads-up river as an oracle for the E3 sampler (#414).

`expected_update` is the intended update of one pass of `solver.VectorCFR` with its strategy frozen,
per deal (divided by the deal mass Z), computed over every combo pair at once. `RiverSampler` makes the
same update from one sampled deal at a time as stalker/e3/mccfr.py does: deal both hands, explore every
action of the traverser, sample the other player's action from the current strategy, `R += vals - v`
at the traverser's rows and `S += sigma` at the other's. The keys must not move during the pass
(`keyer=None`, or `key_ranges="initial"`), since the oracle compares updates of one fixed abstraction.

    python -m stalker.vcfr.sampled        # noise of the sampled update against samples (reference numbers)
"""
from __future__ import annotations

import json
import sys

import numpy as np

from stalker.core.cards import cards
from stalker.vcfr.river import Node, RiverGame
from stalker.vcfr.solver import DEFAULT_BOARD, VectorCFR, regret_match, tp_keyer

Tables = dict[object, np.ndarray]


def _frozen(m: VectorCFR) -> Tables:
    return {tid: regret_match(r) for tid, r in m.regret.items()}


def _static(m: VectorCFR) -> None:
    if m.keyer is not None and m.key_ranges != "initial":
        raise ValueError("the oracle needs keys fixed for the pass: use keyer=None or key_ranges='initial'")


def _add(t: Tables, tid, rows, nrows: int, x: np.ndarray) -> None:
    if tid not in t:
        t[tid] = np.zeros((nrows, x.shape[1]))
    if rows is None:
        t[tid] += x
    else:
        np.add.at(t[tid], rows, x)


def expected_update(m: VectorCFR, p: int) -> tuple[Tables, Tables]:
    """Intended (regret, average) increments per deal of the pass with traverser p, strategy frozen.

    A deal (i, j) has chance pi_c = init_0[i] init_1[j] / Z over non-overlapping pairs. The regret row
    of my combo i gets pi_c pi_-p summed over j = init_p[i] x (counterfactual value) / Z; the average
    row of the other player's combo j gets pi_c pi_q summed over my i = r_q[j] x live(init_p)[j] / Z."""
    _static(m)
    g = m.game
    z = float(g.init[0] @ g.sd.card_mass(g.init[1]))
    sig = _frozen(m)
    reg: Tables = {}
    avg: Tables = {}

    def walk(node: Node, r: list[np.ndarray]) -> np.ndarray:
        if node.kind != "act":
            return g.terminal_value(node, p, r[1 - p])
        q = node.player
        tid, rows, nrows = m._rows(node, r[q], r[1 - q])
        tab = sig.get(tid, np.full((nrows, len(node.children)), 1.0 / len(node.children)))
        s = tab if rows is None else tab[rows]
        if q == p:
            vals = np.stack([walk(ch, r) for ch in node.children], axis=1)
            v = (s * vals).sum(axis=1)
            _add(reg, tid, rows, nrows, g.init[p][:, None] * (vals - v[:, None]) / z)
            return v
        _add(avg, tid, rows, nrows, (r[q] * g.sd.card_mass(g.init[1 - q]) / z)[:, None] * s)
        out = np.zeros(g.sd.n)
        for i, ch in enumerate(node.children):
            rr = list(r)
            rr[q] = r[q] * s[:, i]
            out += walk(ch, rr)
        return out

    walk(g.root, list(g.init))
    return reg, avg


class RiverSampler:
    """The E3 sampler's update on a river subgame, strategy and keys frozen from `m`."""

    def __init__(self, m: VectorCFR):
        _static(m)
        self.m, self.g = m, m.game
        sig = _frozen(m)
        self.at: dict[int, tuple[object, np.ndarray, np.ndarray, int]] = {}   # node -> (tid, row per combo, sigma, rows)
        for nd in self.g.decision_nodes():
            q = nd.player
            tid, rows, nrows = m._rows(nd, self.g.init[q], self.g.init[1 - q])
            rows = np.arange(self.g.sd.n) if rows is None else rows
            tab = sig.get(tid, np.full((nrows, len(nd.children)), 1.0 / len(nd.children)))
            self.at[nd.id] = (tid, rows, tab, nrows)
        sd = self.g.sd
        self.first = self.g.init[0] * sd.card_mass(self.g.init[1])
        self.first = self.first / self.first.sum()

    def deal(self, rng: np.random.Generator) -> tuple[int, int]:
        sd = self.g.sd
        i = int(rng.choice(sd.n, p=self.first))
        w = self.g.init[1] * ~np.isin(sd.cards, sd.cards[i]).any(axis=1)
        return i, int(rng.choice(sd.n, p=w / w.sum()))

    def sample(self, p: int, rng: np.random.Generator, reg: Tables, avg: Tables) -> None:
        """Add one sampled deal's update with traverser p into `reg` and `avg`."""
        hands = self.deal(rng)
        rank = self.g.sd.rank

        def table(t: Tables, tid, nrows: int, m: int) -> np.ndarray:
            if tid not in t:
                t[tid] = np.zeros((nrows, m))
            return t[tid]

        def walk(node: Node) -> float:
            if node.kind == "fold":
                return -node.contrib[p] if node.player == p else node.contrib[1 - p]
            if node.kind == "show":
                return node.contrib[p] * float(np.sign(rank[hands[p]] - rank[hands[1 - p]]))
            q = node.player
            tid, rows, tab, nrows = self.at[node.id]
            row = rows[hands[q]]
            s = tab[row]
            if q == p:
                vals = np.array([walk(ch) for ch in node.children])
                table(reg, tid, nrows, len(s))[row] += vals - s @ vals
                return float(s @ vals)
            table(avg, tid, nrows, len(s))[row] += s
            return walk(node.children[int(rng.choice(len(s), p=s))])

        walk(self.g.root)


def flat(parts: list[tuple[Tables, Tables]], like: list[tuple[Tables, Tables]]) -> np.ndarray:
    """The increments of `parts` laid out as the tables of `like` (missing tables are zero)."""
    out = []
    for (reg, avg), (lr, la) in zip(parts, like):
        for t, ref in ((reg, lr), (avg, la)):
            out += [t.get(tid, np.zeros_like(x)).ravel() for tid, x in sorted(ref.items(), key=lambda kv: str(kv[0]))]
    return np.concatenate(out)


def noise_curve(m: VectorCFR, ns: tuple[int, ...], seed: int = 0) -> list[dict]:
    """Relative L2 error of the mean of n sampled deals (both traversers) against `expected_update`."""
    rng = np.random.default_rng(seed)
    exact = [expected_update(m, p) for p in (0, 1)]
    target = flat(exact, exact)
    sampler = RiverSampler(m)
    acc: list[tuple[Tables, Tables]] = [({}, {}), ({}, {})]
    out, done = [], 0
    for n in sorted(ns):
        for _ in range(n - done):
            for p in (0, 1):
                sampler.sample(p, rng, *acc[p])
        done = n
        err = float(np.linalg.norm(flat(acc, exact) / n - target) / np.linalg.norm(target))
        out.append({"samples": n, "rel_err": round(err, 5), "rel_err_x_sqrt_n": round(err * float(np.sqrt(n)), 3)})
    return out


def skewed_ranges(game_board: tuple[int, ...], seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Two non-uniform ranges (most combos at weight 0.05-1, a tenth at weight 0): the case where a combo's
    own range weight matters to the scatter over a key."""
    rng = np.random.default_rng(seed)
    n = RiverGame(game_board, stack=1.0, bets=(1.0,), raises=()).sd.n
    out = []
    for _ in range(2):
        r = rng.uniform(0.05, 1.0, n)
        r[rng.random(n) < 0.1] = 0.0
        out.append(r)
    return out[0], out[1]


def main(argv=None) -> int:
    board = tuple(cards(DEFAULT_BOARD))
    g = RiverGame(board, stack=1.0, bets=(1.0,), raises=(), raise_cap=2, ranges=skewed_ranges(board))
    m = VectorCFR(g, tp_keyer(5), key_ranges="initial")
    m.iterate(20)
    print(json.dumps({"board": DEFAULT_BOARD, "key": "tp5, initial ranges", "note": "local reference numbers, not CI",
                      "curve": noise_curve(m, (250, 1000, 4000, 16000), 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
