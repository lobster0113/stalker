"""Local best response (LBR, Lisy & Bowling 2017) for E2: a lower bound on exploitability.

The policy under test is fixed. The LBR player tracks the opponent's range over all 1326 combos by
Bayes from the policy's own action probabilities along the public line (no hidden cards), and at
each of its decisions picks the action with the best value under a one-step look-ahead:
  fold          -> lose what is already in
  check / call  -> no more betting: equity against the range x pot - chips in
  bet / raise   -> opponent folds with the policy's fold probability per combo, otherwise calls;
                   called value uses equity against the continuing range
Averaged over sampled hands, LBR's winnings are a *found* exploitation gain — a lower bound, never a
certificate (referee/GATES.md Gate Q3). Opponent combos are bucketed with the policy's own card
abstraction (`Abstraction`, baseline by default), so a TP-tier policy is read the way it was trained.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from referee.anchors.hu_equity import evaluate_batch
from stalker.core.cards import COMBOS
from stalker.e2 import game as G
from stalker.e2.abstraction import BASELINE, Abstraction

COMBO_ARR = np.array(COMBOS, dtype=np.int64)
EQ_RUNOUTS = 8


def combo_buckets(board: tuple[int, ...], abstraction: Abstraction = BASELINE) -> np.ndarray:
    return abstraction.combo_buckets(tuple(board))


def opp_action_probs(policy, s: G.State, opp: int, board_buckets: np.ndarray) -> np.ndarray:
    """(1326, n_actions) probabilities the policy plays each legal action with each opponent combo.

    `policy` is an MCCFR policy dict (infoset -> probs) or a callable (infoset, legal actions) -> probs.
    """
    acts = G.legal(s)
    hist = "".join(h if len(h) == 1 else h[1:] for h in s.history)
    get = policy if callable(policy) else (lambda key, _acts: policy.get(key))
    out = np.full((len(COMBOS), len(acts)), 1.0 / len(acts))
    for b in np.unique(board_buckets):
        if b < 0:
            continue
        p = get(f"{opp}|{s.street}|{b}|{hist}", acts)
        if p is not None and len(p) == len(acts):
            out[board_buckets == b] = p
    return out


def equity_vs_range(hole, board, w, rng) -> float:
    w = w.copy()
    dead = set(hole) | set(board)
    w[np.isin(COMBO_ARR, list(dead)).any(axis=1)] = 0
    if w.sum() <= 0:
        return 0.5
    live = np.array([c for c in range(52) if c not in dead])
    tot = acc = 0.0
    for _ in range(EQ_RUNOUTS):
        need = 5 - len(board)
        extra = rng.choice(live, size=need, replace=False) if need else np.array([], dtype=np.int64)
        full = np.concatenate([np.array(board, dtype=np.int64), extra])
        ww = np.where(np.isin(COMBO_ARR, extra).any(axis=1), 0, w)
        idx = np.flatnonzero(ww > 0)
        if not len(idx):
            continue
        hands = np.concatenate([COMBO_ARR[idx], np.broadcast_to(full, (len(idx), 5))], axis=1)
        mine = evaluate_batch(np.concatenate([np.array(hole), full])[None, :])[0]
        theirs = evaluate_batch(hands)
        share = np.where(mine > theirs, 1.0, np.where(mine == theirs, 0.5, 0.0))
        acc += float((ww[idx] * share).sum())
        tot += float(ww[idx].sum())
    return acc / tot if tot else 0.5


@dataclass
class LBRResult:
    player: int
    hands: int
    mean_bb: float     # LBR player's average winnings per hand against the policy, in big blinds
    stderr_bb: float


def lbr(policy: dict[str, list[float]], player: int, hands: int, seed: int = 0,
        abstraction: Abstraction = BASELINE) -> LBRResult:
    rng = np.random.default_rng(seed)
    opp = 1 - player
    wins = []
    for _ in range(hands):
        s = G.deal(rng)
        w = np.ones(len(COMBOS))
        w[np.isin(COMBO_ARR, list(s.hole[player])).any(axis=1)] = 0
        while not s.done:
            acts = G.legal(s)
            buckets = combo_buckets(s.board, abstraction)
            if s.to_act == opp:
                probs = opp_action_probs(policy, s, opp, buckets)
                key_b = buckets[[i for i, c in enumerate(COMBOS) if set(c) == set(s.hole[opp])][0]]
                p_row = probs[buckets == key_b][0] if (buckets == key_b).any() else np.full(len(acts), 1 / len(acts))
                a = int(rng.choice(len(acts), p=p_row / p_row.sum()))
                w = w * probs[:, a]
                s = G.apply(s, acts[a])
                continue
            best, best_v = None, -np.inf
            for a in acts:
                v = _value(policy, s, a, w, player, rng, abstraction)
                if v > best_v:
                    best, best_v = a, v
            s = G.apply(s, best)
        v = G.payoff(s) / G.BB
        wins.append(v if player == 0 else -v)
    arr = np.array(wins)
    return LBRResult(player, hands, float(arr.mean()), float(arr.std(ddof=1) / np.sqrt(len(arr))) if hands > 1 else 0.0)


def _value(policy, s: G.State, a: str, w: np.ndarray, me: int, rng, abstraction: Abstraction = BASELINE) -> float:
    """One-step look-ahead value (chips) of action `a` for the LBR player."""
    opp = 1 - me
    if a == "f":
        return -s.total[me]
    ns = G.apply(s, a)
    if ns.done or ns.to_act == me or a in ("c", "k"):
        # No bet for the opponent to answer: assume no more betting to showdown.
        eq = equity_vs_range(s.hole[me], ns.board if ns.done else s.board, w, rng) if not ns.folded else 1.0
        pot = ns.total[0] + ns.total[1]
        return eq * pot - ns.total[me]
    probs = opp_action_probs(policy, ns, opp, combo_buckets(ns.board, abstraction))
    acts = G.legal(ns)
    fold = probs[:, acts.index("f")] if "f" in acts else np.zeros(len(COMBOS))
    pf = float((w * fold).sum() / max(w.sum(), 1e-12))
    cont = w * (1 - fold)
    eq = equity_vs_range(s.hole[me], s.board, cont, rng)
    called_pot = 2 * ns.total[me]
    return pf * ns.total[opp] + (1 - pf) * (eq * called_pot - ns.total[me])


def exploitability_lb(policy, hands: int, seed: int = 0, abstraction: Abstraction = BASELINE) -> dict:
    """Mean of both seats' LBR winnings (bb/hand): a lower bound on exploitability."""
    r0, r1 = lbr(policy, 0, hands, seed, abstraction), lbr(policy, 1, hands, seed + 1, abstraction)
    return {"lbr_bb": round((r0.mean_bb + r1.mean_bb) / 2, 4),
            "stderr_bb": round(float(np.hypot(r0.stderr_bb, r1.stderr_bb) / 2), 4),
            "seat0_bb": round(r0.mean_bb, 4), "seat1_bb": round(r1.mean_bb, 4), "hands": hands}
