"""E1b: heads-up open / 3-bet-shove tree, solved exactly — the ground truth for `plan.vs_raise`.

Tree (chip EV, same model as `referee.anchors.pushfold`: stacks S, SB posts 0.5, BB posts 1, BB ante
`a` is dead money the BB loses with the pot):
    SB: fold | open to r | shove
      after open:  BB: fold | 3-bet shove
          after the 3-bet:  SB: fold | call
      after shove: BB: fold | call
Every leaf is a fold or an all-in showdown, so the 169-class game with exact card removal is
solvable. Training is fictitious play between the two seats (self-play); exploitability is the
exact summed best-response gain.

`plan.vs_raise` (TP v1 candidate, ADR 0011) asks, while choosing the open, what the SB will do if
the BB 3-bets all in. Its answer is the SB's equilibrium call probability at that node.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from referee.anchors import pushfold as P


@dataclass
class Strategy:
    fold: np.ndarray    # SB per class
    open: np.ndarray    # SB per class (fold + open + shove = 1)
    shove: np.ndarray   # SB per class
    call3: np.ndarray   # SB per class: call the 3-bet shove after opening
    bb3: np.ndarray     # BB per class: 3-bet shove versus the open
    bbcall: np.ndarray  # BB per class: call versus the SB shove


class Game:
    def __init__(self, stack: float, ante: float = 0.0, open_to: float = 2.5):
        self.S, self.a, self.r = stack, ante, open_to
        e, p = P._tables()
        self.e, self.p = e, p                       # e[sb, bb] = SB all-in equity; p = joint class mass
        pot = 2 * stack + ante
        self.sb_allin = e * pot - stack             # SB net when all in and called
        self.bb_allin = (1 - e) * pot - stack - ante

    # ---- values given a full strategy profile ----
    def sb_value(self, st: Strategy) -> float:
        p, a, r = self.p, self.a, self.r
        fold = -0.5 * (p.sum(axis=1) * st.fold).sum()
        shove = (p * st.shove[:, None] * (st.bbcall[None, :] * self.sb_allin + (1 - st.bbcall[None, :]) * (1 + a))).sum()
        vs3 = st.call3[:, None] * self.sb_allin + (1 - st.call3[:, None]) * (-r)
        opn = (p * st.open[:, None] * ((1 - st.bb3[None, :]) * (1 + a) + st.bb3[None, :] * vs3)).sum()
        return float(fold + shove + opn)

    # ---- best responses (per class, pure) ----
    def sb_best(self, bb3: np.ndarray, bbcall: np.ndarray, allow_open: bool = True) -> tuple[np.ndarray, np.ndarray, float]:
        """Per SB class: (EV of each root action [fold, open, shove], best call3, total BR value)."""
        p, a, r = self.p, self.a, self.r
        fold = -0.5 * p.sum(axis=1)
        shove = (p * (bbcall[None, :] * self.sb_allin + (1 - bbcall[None, :]) * (1 + a))).sum(axis=1)
        reach3 = p * bb3[None, :]
        call_v, fold_v = (reach3 * self.sb_allin).sum(axis=1), -r * reach3.sum(axis=1)
        call3 = (call_v > fold_v).astype(float)
        opn = (p * (1 - bb3[None, :]) * (1 + a)).sum(axis=1) + np.maximum(call_v, fold_v)
        evs = np.stack([fold, opn if allow_open else np.full_like(opn, -np.inf), shove], axis=1)
        return evs, call3, float(evs.max(axis=1).sum())

    def bb_best(self, st: Strategy) -> tuple[np.ndarray, np.ndarray, float]:
        """Per BB class: best 3-bet and call decisions and the BB's total BR value."""
        p, a, r = self.p, self.a, self.r
        w_open = p * st.open[:, None]
        shove3 = (w_open * (st.call3[:, None] * self.bb_allin + (1 - st.call3[:, None]) * r)).sum(axis=0)
        fold3 = -(1 + a) * w_open.sum(axis=0)
        w_sh = p * st.shove[:, None]
        callv, foldv = (w_sh * self.bb_allin).sum(axis=0), -(1 + a) * w_sh.sum(axis=0)
        w_f = p * st.fold[:, None]
        base = (0.5 * w_f).sum()
        total = base + np.maximum(shove3, fold3).sum() + np.maximum(callv, foldv).sum()
        return (shove3 > fold3).astype(float), (callv > foldv).astype(float), float(total)

    def exploitability(self, st: Strategy, allow_open: bool = True) -> float:
        v = self.sb_value(st)
        _, _, sb_br = self.sb_best(st.bb3, st.bbcall, allow_open)
        _, _, bb_br = self.bb_best(st)
        return (sb_br - v) + (bb_br + v)

    def solve(self, iters: int = 4000, allow_open: bool = True) -> Strategy:
        n = 169
        st = Strategy(np.full(n, 1 / 3), np.full(n, 1 / 3), np.full(n, 1 / 3), np.full(n, .5), np.full(n, .5), np.full(n, .5))
        if not allow_open:
            st.open[:] = 0.0
            st.fold[:] = st.shove[:] = 0.5
        reach_open = np.zeros(n)  # SB call3 is averaged weighted by how often each class opens
        for t in range(1, iters + 1):
            evs, call3, _ = self.sb_best(st.bb3, st.bbcall, allow_open)
            root = np.zeros_like(evs)
            root[np.arange(n), evs.argmax(axis=1)] = 1.0
            bb3, bbcall, _ = self.bb_best(st)
            k = 1.0 / (t + 1)
            new_open = st.open + k * (root[:, 1] - st.open)
            # Average call3 by open reach so the delivered node strategy matches the average opener.
            w_old, w_new = reach_open * (1 - k), k * root[:, 1]
            st.call3 = np.where(w_old + w_new > 0, (st.call3 * w_old + call3 * w_new) / np.maximum(w_old + w_new, 1e-300), call3)
            reach_open = w_old + w_new
            st.fold += k * (root[:, 0] - st.fold)
            st.open = new_open
            st.shove += k * (root[:, 2] - st.shove)
            st.bb3 += k * (bb3 - st.bb3)
            st.bbcall += k * (bbcall - st.bbcall)
        return st


def plan_vs_raise(game: Game, st: Strategy, min_open: float = 0.05) -> dict[str, float]:
    """`plan.vs_raise` ground truth: SB call probability against the 3-bet shove, for classes that open."""
    from stalker.core.cards import HAND_CLASSES

    return {c: round(float(st.call3[i]), 4) for i, c in enumerate(HAND_CLASSES) if st.open[i] >= min_open}


def table(stacks=(10.0, 12.5, 15.0, 20.0, 25.0), ante: float = 0.0, iters: int = 3000) -> list[dict]:
    rows = []
    for s in stacks:
        g = Game(s, ante)
        st = g.solve(iters)
        mass = g.p.sum(axis=1)
        opened = st.open * mass
        rows.append({"stack": s, "ante": ante, "iters": iters, "exploitability": round(g.exploitability(st), 5),
                     "sb_value": round(g.sb_value(st), 5),
                     "sb_open": round(float(opened.sum()), 4), "sb_shove": round(float((st.shove * mass).sum()), 4),
                     "sb_call_vs_3bet_given_open": round(float((opened * st.call3).sum() / max(opened.sum(), 1e-12)), 4),
                     "bb_3bet_vs_open": round(float((st.bb3 * g.p.sum(axis=0)).sum()), 4)})
    return rows


if __name__ == "__main__":
    import json
    import sys

    for row in table(iters=int(sys.argv[1]) if len(sys.argv) > 1 else 3000):
        print(json.dumps(row), flush=True)
