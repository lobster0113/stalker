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

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from stalker.e2.eq_view import COMBO_ARR, N, combo_index, equity_vs
from stalker.e3 import game as G
from stalker.e3 import tp_key as K


def seat_probs(policy, s: G.State, seat: int, ranges, k: int, depth: str = "full") -> np.ndarray:
    """(1326, n_actions): the policy's action probabilities for `seat` at `s`, per combo."""
    acts = G.legal(s)
    public = K.public_key(s, seat, depth)
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


OVERBETS = (1.5, 2.0)    # postflop bets as a fraction of the pot that the training menu does not have


class Extra(NamedTuple):
    """An off-menu bet or raise the LBR seat may choose: `to` chips on this street, read by the policy as `menu`."""
    to: int
    menu: str


def _top(s: G.State) -> float:
    """The bet-to at or above which the state's rules count a size as all in (see `G._offered`)."""
    room = s.stack[s.to_act] + s.bet[s.to_act]
    return room - G.BB if G.street_cap(s) is not None else min(room - G.BB, G.ALLIN_MERGE * room)


def translate_size(s: G.State, to: int) -> str:
    """The menu action the policy reads an off-menu bet or raise to `to` chips as (s = state before it).

    Nearest size the state's menu offers (v1, tp6 or real, by chips); a tie takes the larger. All in (or more)
    is "a"; with nothing to call the all-in is a candidate too. Facing a bet only the menu's raise sizes
    compete (v1 has one, "r"). Nearest, not pseudo-harmonic: the key already carries the real price
    through the pot-odds and SPR steps, so the label only has to place the action on the menu for the
    initiative flag and the range update, and nearest is the simplest deterministic rule."""
    p = s.to_act
    room = s.stack[p] + s.bet[p]
    if to >= room:
        return "a"
    sizes = dict(G._offered(s))
    if s.to_call() == 0:
        sizes["a"] = room
    if not sizes:
        return "a"
    return min(sizes, key=lambda m: (abs(sizes[m] - to), -sizes[m]))


def extra_actions(s: G.State) -> list[Extra]:
    """Off-menu postflop sizes for the seat to act: overbets with nothing to call, a minimum raise when
    facing a bet. Only sizes the state's menu lacks (same chips as an offered size does not count) and
    short of all in (the all-in covers the rest). Honors the state's `raise_cap`."""
    p = s.to_act
    call = s.to_call()
    if (s.street == 0 or s.stack[p] <= call or not [i for i in s.active() if i != p]
            or (G.street_cap(s) is not None and s.raises >= G.street_cap(s))):
        return []
    on_menu = {t for _, t in G._offered(s)}
    top = _top(s)
    if call > 0:
        to = max(s.bet) + s.last_raise
        return [Extra(to, translate_size(s, to))] if to < top and to not in on_menu else []
    out = []
    for frac in OVERBETS:
        to = s.bet[p] + max(G.BB, int(round(s.pot * frac)))
        if to < top and to not in on_menu:
            out.append(Extra(to, translate_size(s, to)))
    return out


def _step(s: G.State, a) -> G.State:
    return G.apply_to(s, a.to, a.menu) if isinstance(a, Extra) else G.apply(s, a)


def _as_actor(s: G.State, q: int) -> G.State:
    return s._replace(to_act=q)


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


def lbr(policy, seat: int, hands: int, seed: int = 0, k: int = 5, n: int = 6, depth: str = "full",
        extra_sizes: bool = False) -> LBRResult:
    """`extra_sizes`: the LBR seat may also bet 150% / 200% of the pot and min-raise postflop, sizes the
    policy never trained on (#343). A superset of its default actions, so it measures at least as much."""
    rng = np.random.default_rng(seed)
    wins = []
    for _ in range(hands):
        s = G.deal(rng, n)
        mine = np.isin(COMBO_ARR, list(s.hole[seat])).any(axis=1)
        ranges = K.initial_ranges(n)        # the policy's public beliefs, every seat
        while not s.done:
            p = s.to_act
            probs = seat_probs(policy, s, p, ranges, k, depth)
            acts = G.legal(s)
            if p != seat:
                row = probs[combo_index(s.hole[p])]
                a = int(rng.choice(len(acts), p=row / row.sum()))
            else:
                cands = acts + (extra_actions(s) if extra_sizes else [])
                vals = [_value(policy, s, x, ranges, mine, seat, k, depth) for x in cands]
                a = int(np.argmax(vals))
            chosen = cands[a] if p == seat else acts[a]
            if isinstance(chosen, Extra):   # the policy's belief about this seat sees the nearest menu action
                a = acts.index(chosen.menu) if chosen.menu in acts else acts.index("a")
            ranges = list(ranges)
            ranges[p] = ranges[p] * probs[:, a]
            s = _step(s, chosen)
        wins.append(float(G.payoff(s)[seat]) / G.BB)
    arr = np.array(wins)
    se = float(arr.std(ddof=1) / np.sqrt(len(arr))) if hands > 1 else 0.0
    return LBRResult(seat, hands, float(arr.mean()), se)


def _value(policy, s: G.State, a: str, ranges, mine: np.ndarray, me: int, k: int, depth: str) -> float:
    if a == "f":
        return -float(s.total[me])
    opps = [q for q in s.live() if q != me]
    w = {q: np.where(mine, 0.0, ranges[q]) for q in opps}
    ns = _step(s, a)
    if a in ("k", "c") or ns.done:
        # Only the dealt board: a call that ends the hand deals the runout into `ns`, and reading it
        # would let LBR call only when it wins (clairvoyance, #257 review). Equity integrates the rest.
        return _eq_all(s.hole[me], s.board, list(w.values())) * ns.pot - ns.total[me]
    # A bet or raise: who folds?
    pf, cont = {}, {}
    for q in opps:
        if ns.folded[q] or ns.stack[q] == 0:
            pf[q], cont[q] = 0.0, w[q]
            continue
        qs = _as_actor(ns, q)
        acts = G.legal(qs)
        pr = seat_probs(policy, qs, q, ranges, k, depth)
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


def exploitability_lb(policy, hands: int, seed: int = 0, k: int = 5, n: int = 6, seats=None, depth: str = "full",
                      extra_sizes: bool = False) -> dict:
    """Mean over seats of the LBR player's winnings (bb/hand): a lower bound on one-seat exploitation."""
    seats = list(range(n)) if seats is None else list(seats)
    rs = [lbr(policy, q, hands, seed + 101 * q, k, n, depth, extra_sizes) for q in seats]
    return {"lbr_bb": round(float(np.mean([r.mean_bb for r in rs])), 4),
            "stderr_bb": round(float(np.sqrt(sum(r.stderr_bb ** 2 for r in rs)) / len(rs)), 4),
            "by_seat": {G.position_names(n)[r.seat]: round(r.mean_bb, 4) for r in rs}, "hands": hands}
