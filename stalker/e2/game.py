"""E2 game: heads-up NLHE, 25BB effective, one hand, chip EV, fixed betting abstraction (ADR 0012).

Chips are integers with BB = 100. Player 0 is the button/SB (acts first preflop), player 1 the BB
(acts first postflop). Actions are labels from a fixed menu so the betting tree is finite:
  preflop: f, c (call or check), r (raise: open to 2.5BB, then 3x, then 2.2x the current bet), a (all in)
  postflop, nothing to call: k (check), b33, b75 (bet that share of the pot), a
  postflop, facing a bet: f, c, r (raise to 3x the bet), a
At most RAISE_CAP raises per street; after that only call/fold/all-in. A size that would put a
player within one BB of all in is not offered (the all-in covers it). The state is immutable;
`apply` returns a new state.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from stalker.core.evaluator import evaluate

BB = 100
SB = 50
STACK = 25 * BB
RAISE_CAP = 3
PREFLOP_RAISE = (2.5, 3.0, 2.2)  # raise-to: open to 2.5BB, then multiples of the current bet


@dataclass(frozen=True)
class State:
    hole: tuple[tuple[int, int], tuple[int, int]]
    deck: tuple[int, ...]                 # remaining cards; the board is dealt from the front
    stack: tuple[int, int] = (STACK - SB, STACK - BB)
    bet: tuple[int, int] = (SB, BB)       # chips put in on this street
    total: tuple[int, int] = (SB, BB)     # chips put in this hand
    street: int = 0
    board: tuple[int, ...] = ()
    to_act: int = 0
    raises: int = 1                       # the BB counts as the first "raise" preflop
    last_raise: int = BB                  # size of the last raise increment
    acted: tuple[bool, bool] = (False, False)
    history: tuple[str, ...] = ()         # e.g. ("r", "c", "/", "k", "b33", ...) with "/" between streets
    folded: int | None = None
    done: bool = False

    @property
    def pot(self) -> int:
        return self.total[0] + self.total[1]

    def to_call(self, p: int | None = None) -> int:
        p = self.to_act if p is None else p
        return max(self.bet) - self.bet[p]


def deal(rng: np.random.Generator) -> State:
    d = [int(c) for c in rng.permutation(52)]
    return State(hole=((d[0], d[1]), (d[2], d[3])), deck=tuple(d[4:]))


def _raise_to(s: State) -> int:
    cur = max(s.bet)
    if s.street == 0:
        k = min(s.raises - 1, len(PREFLOP_RAISE) - 1)
        return int(round(PREFLOP_RAISE[0] * BB)) if k == 0 else int(round(cur * PREFLOP_RAISE[k]))
    return 3 * cur


def legal(s: State) -> list[str]:
    if s.done:
        return []
    p = s.to_act
    call = s.to_call()
    room = s.stack[p] + s.bet[p]                     # most this player can have in on this street
    acts: list[str] = []
    if call > 0:
        acts.append("f")
    acts.append("c" if (call > 0 or s.street == 0) else "k")
    if s.stack[p] > call and s.stack[1 - p] > 0:     # can still put more in, and someone to bet into
        if s.raises < RAISE_CAP + (1 if s.street == 0 else 0):
            if call > 0 or s.street == 0:
                to = max(_raise_to(s), max(s.bet) + s.last_raise)
                if to < room - BB:
                    acts.append("r")
            else:
                for name, frac in (("b33", 0.33), ("b75", 0.75)):
                    amt = max(BB, int(round(s.pot * frac)))
                    if s.bet[p] + amt < room - BB:
                        acts.append(name)
        acts.append("a")
    return acts


def _amount_to(s: State, a: str) -> int:
    """Chips this player's street bet goes up to."""
    p = s.to_act
    room = s.stack[p] + s.bet[p]
    if a == "a":
        return room
    if a == "c":
        return min(max(s.bet), room)
    if a == "r":
        return max(_raise_to(s), max(s.bet) + s.last_raise)
    if a in ("b33", "b75"):
        return s.bet[p] + max(BB, int(round(s.pot * (0.33 if a == "b33" else 0.75))))
    raise ValueError(a)


def _deal_street(s: State) -> State:
    n = 3 if s.street == 0 else 1
    return replace(s, street=s.street + 1, board=s.board + s.deck[:n], deck=s.deck[n:], bet=(0, 0), to_act=1,
                   raises=0, last_raise=BB, acted=(False, False), history=s.history + ("/",))


def _close_street(s: State) -> State:
    if s.street == 3:
        return replace(s, done=True)
    if 0 in s.stack:  # someone is all in: run the board out, no more betting
        while s.street < 3:
            s = _deal_street(s)
        return replace(s, done=True)
    return _deal_street(s)


def apply(s: State, a: str) -> State:
    if a not in legal(s):
        raise ValueError(f"illegal action {a!r} after {s.history}; legal: {legal(s)}")
    p, o = s.to_act, 1 - s.to_act
    if a == "f":
        return replace(s, folded=p, done=True, history=s.history + ("f",))
    to = s.bet[p] if a == "k" else _amount_to(s, a)
    add = to - s.bet[p]
    stack, bet, total = list(s.stack), list(s.bet), list(s.total)
    stack[p] -= add
    bet[p] = to
    total[p] += add
    raised = to > max(s.bet)
    acted = [False, False] if raised else list(s.acted)
    acted[p] = True
    ns = replace(s, stack=tuple(stack), bet=tuple(bet), total=tuple(total), history=s.history + (a,),
                 raises=s.raises + int(raised), last_raise=max(s.last_raise, to - max(s.bet)) if raised else s.last_raise,
                 acted=(acted[0], acted[1]), to_act=o)
    # Closed: both acted with equal bets, or this player called all in for less than the bet.
    if (all(ns.acted) and bet[0] == bet[1]) or (stack[p] == 0 and bet[p] <= bet[o]):
        return _close_street(ns)
    return ns


def payoff(s: State) -> int:
    """Chips player 0 wins (negative: loses) relative to the start of the hand."""
    if not s.done:
        raise ValueError("hand is not over")
    if s.folded is not None:
        return -s.total[0] if s.folded == 0 else s.total[1]
    # Uncalled chips go back: each side risks at most what the other matched.
    risk = min(s.total)
    v0, v1 = evaluate(list(s.hole[0]) + list(s.board)), evaluate(list(s.hole[1]) + list(s.board))
    return risk if v0 > v1 else -risk if v0 < v1 else 0


def public_tree_size() -> dict[str, int]:
    """Decision nodes of the betting tree per street (cards ignored)."""
    rng = np.random.default_rng(0)
    root = deal(rng)
    counts = {"preflop": 0, "flop": 0, "turn": 0, "river": 0}
    names = list(counts)
    seen: set[tuple] = set()
    stack = [root]
    while stack:
        s = stack.pop()
        if s.done:
            continue
        key = s.history
        if key in seen:
            continue
        seen.add(key)
        counts[names[s.street]] += 1
        for a in legal(s):
            stack.append(apply(s, a))
    return counts
