"""N-seat local best response for E3 (#197): a lower bound on how much one seat can exploit a policy.

One seat (the LBR player) exploits; every other seat follows the policy under test. The LBR player
tracks each opponent's range by Bayes from the policy's own strategy along the public line (no
hidden cards), and at each of its decisions takes the action with the best one-step value:
  fold          -> lose what is already in
  check / call  -> no more betting: P(beat every remaining opponent) x pot - chips in
  bet / raise   -> each remaining opponent folds with the policy's fold probability for its range
                   (opponents treated as independent); if anyone continues, the value is the equity
                   against the continuing ranges times the expected pot
P(beat all) is the product of equities against each opponent (the same approximation the TP key
uses). The policy is read exactly as it was trained: same TP keys, same equity steps, same public
ranges (the policy's beliefs, which include its belief about the LBR seat). The result is a found
exploitation gain — a lower bound, never a certificate (referee/GATES.md Gate Q3).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from stalker.e2.eq_view import COMBO_ARR, N, combo_index, equity_vs
from stalker.e3 import game as G
from stalker.e3 import tp_key as K


def seat_probs(policy, s: G.State, seat: int, ranges, k: int) -> np.ndarray:
    """(1326, n_actions): the policy's action probabilities for `seat` at `s`, per combo."""
    acts = G.legal(s)
    public = K.public_key(s, seat)
    steps = K.equity_steps(s, seat, ranges, k)
    out = np.full((N, len(acts)), 1.0 / len(acts))
    for v in np.unique(steps):
        if v < 0:
            continue
        p = policy.get(K.key(public, int(v))) if not callable(policy) else policy(K.key(public, int(v)), acts)
        if p is not None and len(p) == len(acts):
            out[steps == v] = p
    out[steps < 0] = 0.0
    return out


def _as_actor(s: G.State, q: int) -> G.State:
    return replace(s, to_act=q)


def _eq_all(hole, board, weights: list[np.ndarray]) -> float:
    i = combo_index(hole)
    eq = 1.0
    for w in weights:
        if w.sum() <= 0:
            continue
        eq *= float(np.nan_to_num(equity_vs(tuple(board), w)[i], nan=0.5))
    return eq


@dataclass
class LBRResult:
    seat: int
    hands: int
    mean_bb: float
    stderr_bb: float


def lbr(policy, seat: int, hands: int, seed: int = 0, k: int = 5, n: int = 6) -> LBRResult:
    rng = np.random.default_rng(seed)
    wins = []
    for _ in range(hands):
        s = G.deal(rng, n)
        mine = np.isin(COMBO_ARR, list(s.hole[seat])).any(axis=1)
        ranges = K.initial_ranges(n)        # the policy's public beliefs, every seat
        while not s.done:
            p = s.to_act
            probs = seat_probs(policy, s, p, ranges, k)
            acts = G.legal(s)
            if p != seat:
                row = probs[combo_index(s.hole[p])]
                a = int(rng.choice(len(acts), p=row / row.sum()))
            else:
                vals = [_value(policy, s, x, ranges, mine, seat, k) for x in acts]
                a = int(np.argmax(vals))
            ranges = list(ranges)
            ranges[p] = ranges[p] * probs[:, a]
            s = G.apply(s, acts[a])
        wins.append(float(G.payoff(s)[seat]) / G.BB)
    arr = np.array(wins)
    se = float(arr.std(ddof=1) / np.sqrt(len(arr))) if hands > 1 else 0.0
    return LBRResult(seat, hands, float(arr.mean()), se)


def _value(policy, s: G.State, a: str, ranges, mine: np.ndarray, me: int, k: int) -> float:
    if a == "f":
        return -float(s.total[me])
    opps = [q for q in s.live() if q != me]
    w = {q: np.where(mine, 0.0, ranges[q]) for q in opps}
    ns = G.apply(s, a)
    if a in ("k", "c") or ns.done:
        board = ns.board if ns.done else s.board
        return _eq_all(s.hole[me], board, list(w.values())) * ns.pot - ns.total[me]
    # A bet or raise: who folds?
    pf, cont = {}, {}
    for q in opps:
        if ns.folded[q] or ns.stack[q] == 0:
            pf[q], cont[q] = 0.0, w[q]
            continue
        qs = _as_actor(ns, q)
        acts = G.legal(qs)
        pr = seat_probs(policy, qs, q, ranges, k)
        fold = pr[:, acts.index("f")] if "f" in acts else np.zeros(N)
        tot = w[q].sum()
        pf[q] = float((w[q] * fold).sum() / tot) if tot > 0 else 1.0
        cont[q] = w[q] * (1 - fold)
    p_all = float(np.prod(list(pf.values())))
    win_now = ns.pot - ns.total[me]
    callers = [q for q in opps if pf[q] < 1.0]
    called_pot = ns.pot + sum((1 - pf[q]) * max(ns.bet[me] - ns.bet[q], 0) for q in opps)
    eq = _eq_all(s.hole[me], s.board, [cont[q] for q in callers])
    return p_all * win_now + (1 - p_all) * (eq * called_pot - ns.total[me])


def exploitability_lb(policy, hands: int, seed: int = 0, k: int = 5, n: int = 6, seats=None) -> dict:
    """Mean over seats of the LBR player's winnings (bb/hand): a lower bound on one-seat exploitation."""
    seats = list(range(n)) if seats is None else list(seats)
    rs = [lbr(policy, q, hands, seed + 101 * q, k, n) for q in seats]
    return {"lbr_bb": round(float(np.mean([r.mean_bb for r in rs])), 4),
            "stderr_bb": round(float(np.sqrt(sum(r.stderr_bb ** 2 for r in rs)) / len(rs)), 4),
            "by_seat": {G.position_names(n)[r.seat]: round(r.mean_bb, 4) for r in rs}, "hands": hands}
