"""E3 game: N-handed NLHE (6 by default, up to 9), 100BB, one hand, chip EV, fixed betting menu (#194).

Same action labels as E2 (stalker/e2/game.py, ADR 0012) so TP keys and tools carry over:
  preflop: f, c (call or check), r (open to 2.5BB, then 3x, then 2.2x the current bet), a (all in)
  postflop, nothing to call: k, b33, b75, a
  postflop, facing a bet: f, c, r (raise to 3x the bet), a
At most RAISE_CAP raises per street; preflop that is RAISE_CAP raises after the big blind. A size
that would put a player within one BB of all in is not offered (the all-in covers it).

`menu="tp6"` (#339) widens the sizes to the TP.md section 6 buckets; "r" keeps the middle size so the
persona rules (stalker/e2/personas.py) still find a raise:
  preflop, unopened: r22, r, r3 (open to 2.2 / 2.5 / 3 BB); with limpers only "r", the isolation raise
    to 2.5BB + 1BB per limper (the small blind completing counts as a limper)
  facing a bet or raise (any street): r25, r, r4 (raise to 2.5x / 3x / 4x the current bet)
  postflop, nothing to call: k, b33, b50, b75, b100, b150, a
Every size is at least the minimum raise; a size that lands on the same amount as a smaller one is
offered once. `raise_cap=None` removes the per-street cap; then a raise to ALLIN_MERGE of the stack or
more is merged into the all-in (raise wars end in a few steps instead of creeping up by min-raises).
Both are State fields, so a hand keeps its rules; `deal` takes them, defaulting to `rules(...)`.

Seats are numbered in preflop order: 0 = UTG ... n-3 = BTN, n-2 = SB, n-1 = BB. Postflop the SB
acts first. Heads-up (n = 2) the SB is the button: first preflop, last postflop. Every player starts with the same stack, so an all-in is the largest possible
contribution and no side pot can arise; showdowns split one pot (odd chips to the first winner
in postflop order). Chips are integers with BB = 100. The state is immutable.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import NamedTuple

import numpy as np

from stalker.core.evaluator import evaluate

BB = 100
SB = 50
STACK = 100 * BB
RAISE_CAP = 3
PREFLOP_RAISE = (2.5, 3.0, 2.2)
MENUS = ("v1", "tp6")
TP6_OPEN = (("r22", 2.2), ("r", 2.5), ("r3", 3.0))           # BB
TP6_RAISE = (("r25", 2.5), ("r", 3.0), ("r4", 4.0))          # x the current bet
TP6_BET = (("b33", 0.33), ("b50", 0.5), ("b75", 0.75), ("b100", 1.0), ("b150", 1.5))   # x the pot
ISO_BASE, ISO_PER_LIMPER = 250, 100
ALLIN_MERGE = 0.8      # raise_cap=None: a raise to >= 80% of the stack is the all-in
_DEFAULT = {"menu": "v1", "raise_cap": RAISE_CAP}
_UNSET = object()      # raise_cap=None means "no cap", so "not given" needs its own marker
POSITIONS = {6: ("UTG", "HJ", "CO", "BTN", "SB", "BB"),
             9: ("UTG", "UTG1", "UTG2", "LJ", "HJ", "CO", "BTN", "SB", "BB")}


def position_names(n: int) -> tuple[str, ...]:
    if n == 2:
        return ("SB", "BB")  # heads-up: the small blind is the button
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
    menu: str = "v1"
    raise_cap: int | None = RAISE_CAP

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


@contextmanager
def rules(menu: str = "v1", raise_cap: int | None = RAISE_CAP):
    """Default rules for `deal` inside the block. The referee evaluators (LBR, field, Gate R replay)
    call `deal(rng, n)`; this lets them run on another menu without changing protected code."""
    if menu not in MENUS:
        raise ValueError(f"menu={menu!r}; known menus: {MENUS}")
    old = dict(_DEFAULT)
    _DEFAULT.update(menu=menu, raise_cap=raise_cap)
    try:
        yield
    finally:
        _DEFAULT.update(old)


def deal(rng: np.random.Generator, n: int = 6, menu: str | None = None, raise_cap=_UNSET) -> State:
    if not 2 <= n <= 9:
        raise ValueError(f"n={n}: E3 supports 2..9 players")
    menu = _DEFAULT["menu"] if menu is None else menu
    raise_cap = _DEFAULT["raise_cap"] if raise_cap is _UNSET else raise_cap
    if menu not in MENUS:
        raise ValueError(f"menu={menu!r}; known menus: {MENUS}")
    d = [int(c) for c in rng.permutation(52)]
    hole = tuple((d[2 * i], d[2 * i + 1]) for i in range(n))
    bet = [0] * n
    bet[n - 2], bet[n - 1] = SB, BB
    stack = tuple(STACK - b for b in bet)
    return State(n=n, hole=hole, deck=tuple(d[2 * n:]), stack=stack, bet=tuple(bet), total=tuple(bet),
                 folded=(False,) * n, acted=(False,) * n, to_act=0, menu=menu, raise_cap=raise_cap)


def postflop_order(n: int) -> list[int]:
    if n == 2:
        return [1, 0]  # heads-up: the big blind acts first after the flop, the button (SB) last
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


def _sizes(s: State) -> list[tuple[str, int]]:
    """(label, bet-to) for every raise or bet size the menu offers here, before the stack checks."""
    cur = max(s.bet)
    p = s.to_act
    if s.menu == "v1":
        if s.to_call() > 0 or s.street == 0:
            return [("r", max(_raise_to(s), cur + s.last_raise))]
        return [(name, s.bet[p] + max(BB, int(round(s.pot * frac)))) for name, frac in (("b33", 0.33), ("b75", 0.75))]
    least = cur + s.last_raise
    if s.street == 0 and s.raises <= 1:
        limpers = sum(1 for i in range(s.n - 1) if s.bet[i] == BB)  # the big blind's own BB is not a limp
        if limpers:
            return [("r", max(least, ISO_BASE + ISO_PER_LIMPER * limpers))]
        return [(name, max(least, int(round(x * BB)))) for name, x in TP6_OPEN]
    if s.to_call() > 0:
        return [(name, max(least, int(round(x * cur)))) for name, x in TP6_RAISE]
    return [(name, s.bet[p] + max(BB, int(round(s.pot * frac)))) for name, frac in TP6_BET]


def _offered(s: State) -> list[tuple[str, int]]:
    p = s.to_act
    room = s.stack[p] + s.bet[p]
    top = room - BB if s.raise_cap is not None else min(room - BB, ALLIN_MERGE * room)
    out: list[tuple[str, int]] = []
    for name, to in _sizes(s):
        if to < top and all(to != t for _, t in out):
            out.append((name, to))
    return out


def legal(s: State) -> list[str]:
    if s.done:
        return []
    p = s.to_act
    call = s.to_call()
    others = [i for i in s.active() if i != p]
    acts: list[str] = []
    if call > 0:
        acts.append("f")
    acts.append("c" if (call > 0 or s.street == 0) else "k")
    if s.stack[p] > call and others:
        cap = s.raise_cap
        if cap is None or s.raises < cap + (1 if s.street == 0 else 0):
            acts.extend(name for name, _ in _offered(s))
        acts.append("a")
    return acts


def _amount_to(s: State, a: str) -> int:
    p = s.to_act
    room = s.stack[p] + s.bet[p]
    if a == "a":
        return room
    if a == "c":
        return min(max(s.bet), room)
    for name, to in _sizes(s):
        if name == a:
            return to
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
    for i in winners:
        out[i] += share
    out[winners[0]] += odd  # all odd chips to the first winner (TDA, as referee/gate_r/settlement.py; #203)
    return out


def random_playout(rng: np.random.Generator, n: int = 6, menu: str | None = None,
                   raise_cap=_UNSET) -> State:
    s = deal(rng, n, menu, raise_cap)
    while not s.done:
        acts = legal(s)
        s = apply(s, acts[int(rng.integers(len(acts)))])
    return s
