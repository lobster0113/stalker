"""Range-vector CFR+ on a public tree, per combo or TP-keyed (#393, research prototype).

Every iteration walks the public tree once per player with both ranges as vectors over all combos: no
deal is sampled, every combo is updated with its exact reach weight (vanilla CFR in vector form, with
the CFR+ regret floor, alternating updates and linear averaging, Tammelin 2014 / Bowling et al. 2015).

Two strategy tables share one code path, a *keyer* that maps each (node, combo) to a table row:

- per combo (`keyer=None`): row = combo, one table per node. This is the unconstrained solution a
  solver computes; on a river subgame it converges to an equilibrium (exploitability -> 0).
- TP-keyed (`tp_keyer`): row = the combo's TP key at that node. Here the key is the `hand.equity` step
  (equity against the opponent's current reach, on a k-step quantile scale over my combos, as
  stalker/e3/tp_key.py does) and, with `public="tp"`, nodes that share the public TP facts (player,
  raise level, pot-odds step, SPR step, legal actions) share one table. Regrets are scatter-added from
  combos into keys and the strategy is gathered back from keys to combos, so the update is the exact
  range-weighted abstraction update. Merging combos breaks perfect recall, so CFR's equilibrium
  guarantee does not carry over; `exploitability` measures what it costs (the "TP cost").

The deployed TP policy reads its keys from public ranges computed as if every player follows the
policy (the info contract, docs/TP.md section 2). `materialize` makes that per-combo strategy, and the
best response is taken against it.

    python -m stalker.vcfr.solver --iters 1000 --k 5 17
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Callable

import numpy as np

from stalker.core.cards import cards
from stalker.vcfr.river import REAL_BETS, REAL_RAISES, Node, RiverGame

POT_ODDS_EDGES = (0.2, 0.3, 0.4)     # stalker/e3/tp_key.py
SPR_EDGES = (1.0, 3.0, 6.0)

# keyer(game, node, r_own, r_opp) -> (table id, row per combo, rows in the table)
# Which public ranges TP features are read from during training (#393; the "current does not settle"
# finding there was a reach bug, corrected in #414).
#   current: the ranges of this iteration's strategy, as stalker/e3/mccfr.py does
#   average: the ranges of the average strategy (the deployed policy), refreshed every `refresh` iterations
#   initial: the subgame's starting ranges (a fixed bucketing of hands)
KEY_RANGES = ("current", "average", "initial")
Keyer = Callable[[RiverGame, Node, np.ndarray, np.ndarray], tuple[object, np.ndarray, int]]


def quantile_steps(x: np.ndarray, k: int) -> np.ndarray:
    """k-step quantile scale of x over equally weighted combos; equal values share a step."""
    vals, inv = np.unique(x, return_inverse=True)
    mass = np.bincount(inv.ravel(), minlength=len(vals)) / len(x)
    mid = np.cumsum(mass) - mass / 2
    return np.minimum((mid * k).astype(np.int64), k - 1)[inv.ravel()]


def public_tp_key(node: Node) -> tuple:
    """The node's public TP facts, as stalker/e3/tp_key.public_key reads them on a heads-up river."""
    pot = node.contrib[0] + node.contrib[1]
    po = 0 if node.to_call <= 0 else 1 + int(np.searchsorted(POT_ODDS_EDGES, node.to_call / (pot + node.to_call), "right"))
    return node.player, min(node.raises, 3), po, node.labels


def identity_keyer(game: RiverGame, node: Node, r_own, r_opp):
    """Every combo its own row, through the TP path: must equal the per-combo solver exactly."""
    return node.id, np.arange(game.sd.n), game.sd.n


def tp_keyer(k: int, public: str = "node") -> Keyer:
    if public not in ("node", "tp"):
        raise ValueError(f"public={public!r}; use 'node' or 'tp'")

    def keyer(game: RiverGame, node: Node, r_own, r_opp):
        steps = quantile_steps(game.sd.equity(r_opp), k)
        return (node.id if public == "node" else public_tp_key(node)), steps, k
    return keyer


def regret_match(r: np.ndarray) -> np.ndarray:
    pos = np.maximum(r, 0.0)
    tot = pos.sum(axis=1, keepdims=True)
    return np.where(tot > 0, pos / np.where(tot > 0, tot, 1.0), 1.0 / r.shape[1])


class VectorCFR:
    def __init__(self, game: RiverGame, keyer: Keyer | None = None, key_ranges: str = "average", refresh: int = 10):
        if key_ranges not in KEY_RANGES:
            raise ValueError(f"key_ranges={key_ranges!r}; use one of {KEY_RANGES}")
        self.game, self.keyer = game, keyer
        self.key_ranges, self.refresh = key_ranges, refresh
        self.regret: dict[object, np.ndarray] = {}
        self.avg: dict[object, np.ndarray] = {}
        self.key_reach: dict[int, list[np.ndarray]] = {}    # node -> ranges the TP features are read from
        self.t = 0
        # Chance weight of my combo: its own range for the regret, times the opponent's live range mass for
        # the average. Uniform ranges make both a constant, but a TP key merging combos of unequal weight
        # needs them, or the scatter counts every combo as equally likely (#414).
        self.live = [game.sd.card_mass(game.init[1]), game.sd.card_mass(game.init[0])]

    def _rows(self, node: Node, r_own, r_opp):
        if self.keyer is None:
            return node.id, None, self.game.sd.n
        q = node.player
        if self.key_ranges == "initial":
            r_own, r_opp = self.game.init[q], self.game.init[1 - q]
        elif self.key_ranges == "average" and node.id in self.key_reach:
            r = self.key_reach[node.id]
            r_own, r_opp = r[q], r[1 - q]
        return self.keyer(self.game, node, r_own, r_opp)

    def _table(self, store, tid, rows, m):
        tab = store.get(tid)
        if tab is None:
            tab = store[tid] = np.zeros((rows, m))
        return tab

    def _sigma(self, node: Node, r):
        q = node.player
        tid, rows, nrows = self._rows(node, r[q], r[1 - q])
        tab = self._table(self.regret, tid, nrows, len(node.children))
        s = regret_match(tab)
        return tid, rows, nrows, (s if rows is None else s[rows])

    def _walk(self, node: Node, p: int, r: list[np.ndarray]) -> np.ndarray:
        g = self.game
        if node.kind != "act":
            return g.terminal_value(node, p, r[1 - p])
        q = node.player
        tid, rows, nrows, sigma = self._sigma(node, r)
        if q == p:
            # Own reach rides down too: the average below weights by it, and the opponent's TP key reads it.
            vals = np.stack([self._walk(ch, p, self._down(r, q, sigma[:, i])) for i, ch in enumerate(node.children)],
                            axis=1)
            v = (sigma * vals).sum(axis=1)
            diff = g.init[p][:, None] * (vals - v[:, None])
            reg = self.regret[tid]
            contrib = (r[q] * self.live[q])[:, None] * sigma * self.t        # linear averaging (CFR+)
            avg = self._table(self.avg, tid, nrows, len(node.children))
            if rows is None:
                reg += diff
                avg += contrib
            else:
                np.add.at(reg, rows, diff)                    # combos -> TP keys
                np.add.at(avg, rows, contrib)
            np.maximum(reg, 0.0, out=reg)                     # CFR+ floor
            return v
        out = np.zeros(g.sd.n)
        for i, ch in enumerate(node.children):
            out += self._walk(ch, p, self._down(r, q, sigma[:, i]))
        return out

    @staticmethod
    def _down(r: list[np.ndarray], q: int, s: np.ndarray) -> list[np.ndarray]:
        rr = list(r)
        rr[q] = r[q] * s
        return rr

    def iterate(self, iters: int = 1) -> None:
        for _ in range(iters):
            if self.keyer is not None and self.key_ranges == "average" and self.t % self.refresh == 0 and self.avg:
                self.materialize(record=True)
            self.t += 1
            for p in (0, 1):
                self._walk(self.game.root, p, list(self.game.init))

    def average_rows(self) -> dict[object, np.ndarray]:
        out = {}
        for tid, a in self.avg.items():
            tot = a.sum(axis=1, keepdims=True)
            out[tid] = np.where(tot > 0, a / np.where(tot > 0, tot, 1.0), 1.0 / a.shape[1])
        return out

    def materialize(self, average: bool = True, record: bool = False) -> dict[int, np.ndarray]:
        """Per-combo strategy at every decision node, keys read from the policy's own public ranges.

        `record` stores those ranges as the ones training reads TP features from (key_ranges="average")."""
        tables = self.average_rows() if average else {t: regret_match(v) for t, v in self.regret.items()}
        out: dict[int, np.ndarray] = {}

        def rec(node: Node, r: list[np.ndarray]):
            if node.kind != "act":
                return
            q = node.player
            if record:
                self.key_reach[node.id] = r
                tid, rows, nrows = self.keyer(self.game, node, r[q], r[1 - q])
            else:
                tid, rows, nrows = self._rows(node, r[q], r[1 - q])
            tab = tables.get(tid)
            if tab is None:
                tab = np.full((nrows, len(node.children)), 1.0 / len(node.children))
            s = tab if rows is None else tab[rows]
            out[node.id] = s
            for i, ch in enumerate(node.children):
                rr = list(r)
                rr[q] = r[q] * s[:, i]
                rec(ch, rr)
        rec(self.game.root, list(self.game.init))
        return out


def _value(game: RiverGame, strat: dict[int, np.ndarray], p: int, br: bool) -> float:
    """Player p's expected value per deal: following `strat` (br=False) or best-responding to it."""

    def rec(node: Node, r_opp: np.ndarray, r_own: np.ndarray) -> np.ndarray:
        if node.kind != "act":
            return game.terminal_value(node, p, r_opp)
        s = strat[node.id]
        if node.player == p:
            vals = np.stack([rec(ch, r_opp, r_own * s[:, i]) for i, ch in enumerate(node.children)], axis=1)
            return vals.max(axis=1) if br else (s * vals).sum(axis=1)
        return sum(rec(ch, r_opp * s[:, i], r_own) for i, ch in enumerate(node.children))

    r_own, r_opp = game.init[p], game.init[1 - p]
    v = rec(game.root, r_opp, r_own)
    z = float(r_own @ game.sd.card_mass(r_opp))
    return float(r_own @ v) / z


def exploitability(game: RiverGame, strat: dict[int, np.ndarray]) -> float:
    """Mean best-response gain over the two seats, in pots (0 at an equilibrium)."""
    return 0.5 * (_value(game, strat, 0, True) + _value(game, strat, 1, True))


def ev(game: RiverGame, strat: dict[int, np.ndarray], p: int) -> float:
    return _value(game, strat, p, False)


def mixed(a: dict[int, np.ndarray], b: dict[int, np.ndarray], game: RiverGame, a_player: int) -> dict[int, np.ndarray]:
    """Strategy profile with player `a_player` from `a` and the other from `b` (head-to-head)."""
    return {nd.id: (a if nd.player == a_player else b)[nd.id] for nd in game.decision_nodes()}


def head_to_head(game: RiverGame, tp: dict[int, np.ndarray], ref: dict[int, np.ndarray]) -> float:
    """TP policy's mean EV over both seats against the reference (pots per deal; < 0 = TP loses)."""
    return 0.5 * (ev(game, mixed(tp, ref, game, 0), 0) + ev(game, mixed(tp, ref, game, 1), 1))


DEFAULT_BOARD = "Ks9h5c4d2s"    # dry, no flush or straight draw finished: a value-vs-bluff river


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Range-vector CFR+ on a heads-up river (reference numbers only)")
    ap.add_argument("--board", default=DEFAULT_BOARD)
    ap.add_argument("--iters", type=int, default=500)
    ap.add_argument("--k", type=int, nargs="*", default=[5, 11, 17])
    ap.add_argument("--menu", choices=["small", "real"], default="small")
    ap.add_argument("--stack", type=float, default=2.0)
    a = ap.parse_args(argv)
    kw = dict(bets=REAL_BETS, raises=REAL_RAISES, raise_cap=3) if a.menu == "real" else {}
    game = RiverGame(tuple(cards(a.board)), stack=a.stack, **kw)
    forms = [("combo", None, "average")]
    forms += [(f"tp{k}", tp_keyer(k), "average") for k in a.k]
    forms += [(f"tp{k}-current", tp_keyer(k), "current") for k in a.k]
    forms += [(f"tp{k}-public", tp_keyer(k, "tp"), "average") for k in a.k]
    rows = []
    ref = None
    for name, keyer, kr in forms:
        m = VectorCFR(game, keyer, kr)
        curve, train = {}, 0.0
        for it in sorted({min(a.iters, x) for x in (10, 100, a.iters)}):
            t0 = time.perf_counter()
            m.iterate(it - m.t)
            train += time.perf_counter() - t0
            curve[it] = round(100 * exploitability(game, m.materialize()), 3)
        strat = m.materialize()
        if ref is None:
            ref = strat
        rows.append({"form": name, "key_ranges": kr if keyer else None, "tables": len(m.regret),
                     "rows": int(sum(v.shape[0] for v in m.regret.values())), "expl_pct_pot": curve,
                     "iters_per_s": round(a.iters / train, 1),
                     "h2h_vs_combo_pct_pot": round(100 * head_to_head(game, strat, ref), 3)})
    print(json.dumps({"board": a.board, "menu": a.menu, "combos": game.sd.n, "decision_nodes": len(game.decision_nodes()),
                      "nodes": len(game.nodes), "note": "local reference numbers, not CI", "rows": rows}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
