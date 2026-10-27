"""E3 game: N-handed NLHE (6 by default, up to 9), 100BB, one hand, chip EV, fixed betting menu (#194).

Same action labels as E2 (stalker/e2/game.py, ADR 0012) so TP keys and tools carry over:
  preflop: f, c (call or check), r (open to 2.5BB, then 3x, then 2.2x the current bet), a (all in)
  postflop, nothing to call: k, b33, b75, a
  postflop, facing a bet: f, c, r (raise to 3x the bet), a
At most RAISE_CAP raises per street (the big blind counts as one preflop). A size that would put a
player within one BB of all in is not offered.

Seats are numbered in preflop order: 0 = UTG ... n-3 = BTN, n-2 = SB, n-1 = BB. Postflop the SB
acts first. Every player starts with the same stack, so an all-in is the largest possible
contribution and no side pot can arise; showdowns split one pot (odd chips to the first winner
in postflop order). Chips are integers with BB = 100. The state is immutable.
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from stalker.core.evaluator import evaluate

BB = 100
SB = 50
STACK = 100 * BB
RAISE_CAP = 3
PREFLOP_RAISE = (2.5, 3.0, 2.2)
POSITIONS = {6: ("UTG", "HJ", "CO", "BTN", "SB", "BB"),
             9: ("UTG", "UTG1", "UTG2", "LJ", "HJ", "CO", "BTN", "SB", "BB")}


def position_names(n: int) -> tuple[str, ...]:
    if n in POSITIONS:
        return POSITIONS[n]
    early = tuple(f"EP{i}" for i in range(n - 3))
    return early + ("BTN", "SB", "BB")


class State(NamedTuple):
    # Immutable; NamedTuple because `_replace` is much cheaper than dataclasses.replace and
    # training creates a state per tree edge.
    n: int
    hole: tuple[tuple[int, int], ...]
    deck: tuple[int, ...]                 # remaining cards; the board is dealt from the front
    stack: tuple[int, ...]
    bet: tuple[int, ...]                  # chips put in on this street
    total: tuple[int, ...]                # chips put in this hand
    folded: tuple[bool, ...]
    acted: tuple[bool, ...]
    street: int = 0
    board: tuple[int, ...] = ()
    to_act: int = 0
    raises: int = 1
    last_raise: int = BB
    history: tuple[str, ...] = ()         # "<seat>:<action>" entries, "/" between streets
    done: bool = False

    @property
    def pot(self) -> int:
        return sum(self.total)

    def to_call(self, p: int | None = None) -> int:
        p = self.to_act if p is None else p
        return max(self.bet) - self.bet[p]

    def live(self) -> list[int]:
        """Players still in the hand."""
        return [i for i in range(self.n) if not self.folded[i]]

    def active(self) -> list[int]:
        """Players still in the hand who can act (not all in)."""
        return [i for i in range(self.n) if not self.folded[i] and self.stack[i] > 0]


def deal(rng: np.random.Generator, n: int = 6) -> State:
    if not 2 <= n <= 9:
        raise ValueError(f"n={n}: E3 supports 2..9 players")
    d = [int(c) for c in rng.permutation(52)]
    hole = tuple((d[2 * i], d[2 * i + 1]) for i in range(n))
    bet = [0] * n
    bet[n - 2], bet[n - 1] = SB, BB
    stack = tuple(STACK - b for b in bet)
    return State(n=n, hole=hole, deck=tuple(d[2 * n:]), stack=stack, bet=tuple(bet), total=tuple(bet),
                 folded=(False,) * n, acted=(False,) * n, to_act=0)


def postflop_order(n: int) -> list[int]:
    return [n - 2, n - 1] + list(range(n - 2))


def _next_to_act(s: State, p: int) -> int:
    order = list(range(s.n)) if s.street == 0 else postflop_order(s.n)
    k = order.index(p)
    for j in order[k + 1:] + order[:k + 1]:
        if not s.folded[j] and s.stack[j] > 0:
            return j
    return p


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
    room = s.stack[p] + s.bet[p]
    others = [i for i in s.active() if i != p]
    acts: list[str] = []
    if call > 0:
        acts.append("f")
    acts.append("c" if (call > 0 or s.street == 0) else "k")
    if s.stack[p] > call and others:
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


def _street_closed(s: State) -> bool:
    act = s.active()
    top = max(s.bet)
    if any(s.bet[i] != top for i in act):
        return False
    return len(act) <= 1 or all(s.acted[i] for i in act)


def _deal_street(s: State) -> State:
    k = 3 if s.street == 0 else 1
    ns = s._replace(street=s.street + 1, board=s.board + s.deck[:k], deck=s.deck[k:], bet=(0,) * s.n,
                 raises=0, last_raise=BB, acted=(False,) * s.n, history=s.history + ("/",))
    first = next((i for i in postflop_order(s.n) if not s.folded[i] and s.stack[i] > 0), s.n - 2)
    return ns._replace(to_act=first)


def _after_close(s: State) -> State:
    if len(s.live()) == 1:
        return s._replace(done=True)
    if len(s.active()) <= 1:  # nobody left to bet against: run the board out
        while s.street < 3:
            s = _deal_street(s)
        return s._replace(done=True)
    if s.street == 3:
        return s._replace(done=True)
    return _deal_street(s)


def apply(s: State, a: str) -> State:
    if a not in legal(s):
        raise ValueError(f"illegal action {a!r} after {s.history}; legal: {legal(s)}")
    p = s.to_act
    hist = s.history + (f"{p}:{a}",)
    if a == "f":
        folded = list(s.folded)
        folded[p] = True
        ns = s._replace(folded=tuple(folded), history=hist)
        if len(ns.live()) == 1:
            return ns._replace(done=True)
    else:
        to = s.bet[p] if a == "k" else _amount_to(s, a)
        add = to - s.bet[p]
        stack, bet, total = list(s.stack), list(s.bet), list(s.total)
        stack[p] -= add
        bet[p] = to
        total[p] += add
        raised = to > max(s.bet)
        acted = [False] * s.n if raised else list(s.acted)
        acted[p] = True
        ns = s._replace(stack=tuple(stack), bet=tuple(bet), total=tuple(total), acted=tuple(acted), history=hist,
                     raises=s.raises + int(raised),
                     last_raise=max(s.last_raise, to - max(s.bet)) if raised else s.last_raise)
    if _street_closed(ns):
        return _after_close(ns)
    return ns._replace(to_act=_next_to_act(ns, p))


def payoff(s: State) -> np.ndarray:
    """Net chips per seat relative to the start of the hand (sums to zero)."""
    if not s.done:
        raise ValueError("hand is not over")
    live = s.live()
    out = -np.array(s.total, dtype=np.int64)
    if len(live) == 1:
        out[live[0]] += s.pot
        return out
    score = {i: evaluate(list(s.hole[i]) + list(s.board)) for i in live}
    best = max(score.values())
    winners = [i for i in postflop_order(s.n) if i in score and score[i] == best]
    share, odd = divmod(s.pot, len(winners))
    for k, i in enumerate(winners):
        out[i] += share + (1 if k < odd else 0)
    return out


def random_playout(rng: np.random.Generator, n: int = 6) -> State:
    s = deal(rng, n)
    while not s.done:
        acts = legal(s)
        s = apply(s, acts[int(rng.integers(len(acts)))])
    return s
