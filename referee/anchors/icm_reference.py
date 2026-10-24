"""ICMizer-equivalent reference v1: N-player (2..9) ICM push/fold and all-in call equilibrium.

Game model (the referee's baseline for Gate A, see referee/GATES.md):
- `Spot.stacks` are in preflop action order; the last two seats are SB and BB (heads-up:
  [SB/button, BB]). Antes are dead money (`ante` from everyone, or `bb_ante` from the BB),
  blinds are live.
- Each seat before the BB either folds or moves all-in. After the first all-in, later seats
  call or fold, and **the first caller ends the action** (overcalls/isolation are not
  modelled). If everyone folds to the BB, the BB takes the pot.
- Hands are the 169 classes. Card removal is modelled only between the two all-in players
  (exact combo-pair counts `N`); fold probabilities of other seats ignore removal.
- Showdown equity counts ties as half a win (ICM value is evaluated at win/lose stacks).
- Terminal stacks are valued by `value_model`: "icm" (Malmuth-Harville via
  `stalker.core.icm`, a player busted in the hand takes the payout of the place they
  finish), "chipev" (chips), with `fgs_depth` d > 0 replacing ICM by the equilibrium value of
  the next hand (button moves one seat, busted seats removed) solved at depth d-1. FGS falls
  back to ICM when the next hand cannot be posted by every seat.
- Every seat must keep chips behind after posting; spots where a post is all-in are rejected.

The equilibrium is computed by fictitious play (average of best responses) until every
player's best-response gain is at most `tol` x prize pool. Ranges are probabilities per
class (mixed strategies allowed).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, Sequence

import numpy as np

from stalker.core.cards import HAND_CLASSES
from stalker.core.icm import icm_equity
from stalker.core.ranges import class_top_pct

from .hu_equity import load as load_equity

N_CLASSES = len(HAND_CLASSES)
CLASS_COMBOS = np.array([6.0 if len(c) == 2 else (4.0 if c[2] == "s" else 12.0)
                         for c in HAND_CLASSES])
PRIOR = CLASS_COMBOS / CLASS_COMBOS.sum()
VALUE_MODELS = ("icm", "chipev")


class SpotError(ValueError):
    pass


@dataclass(frozen=True)
class Spot:
    stacks: tuple[int, ...]
    sb: int
    bb: int
    payouts: tuple[float, ...] = (1.0,)
    ante: int = 0
    bb_ante: int = 0

    def __post_init__(self):
        object.__setattr__(self, "stacks", tuple(self.stacks))
        object.__setattr__(self, "payouts", tuple(float(x) for x in self.payouts))
        n = len(self.stacks)
        if not 2 <= n <= 9:
            raise SpotError(f"{n} players; the reference supports 2..9.")
        if self.ante and self.bb_ante:
            raise SpotError("use either ante (everyone) or bb_ante (big blind), not both.")
        if min(self.sb, self.bb, self.ante, self.bb_ante) < 0 or self.bb <= 0:
            raise SpotError("blinds/antes must be non-negative and bb positive.")
        if any(p < 0 for p in self.payouts):
            raise SpotError("payouts must be non-negative.")
        behind = np.asarray(self.stacks, dtype=float) - self.posts
        if np.any(behind <= 0):
            raise SpotError("every seat needs chips behind after posting; "
                            f"stacks {self.stacks} vs posts {self.posts.tolist()}.")

    @property
    def n(self) -> int:
        return len(self.stacks)

    @property
    def dead(self) -> np.ndarray:
        d = np.full(self.n, float(self.ante))
        d[-1] += self.bb_ante
        return d

    @property
    def blinds(self) -> np.ndarray:
        b = np.zeros(self.n)
        b[-2], b[-1] = self.sb, self.bb
        return b

    @property
    def posts(self) -> np.ndarray:
        return self.dead + self.blinds

    @property
    def prize_pool(self) -> float:
        return float(sum(self.payouts[: self.n]))


def _place_values(stacks: np.ndarray, payouts: Sequence[float]) -> np.ndarray:
    """ICM $ for live seats plus the payout of the place(s) taken by seats busted now."""
    p = list(payouts) + [0.0] * max(0, len(stacks) - len(payouts))
    live = stacks > 0
    m = int(live.sum())
    out = np.zeros(len(stacks))
    out[live] = np.asarray(icm_equity(stacks[live], p[:m]))
    if m < len(stacks):
        out[~live] = np.mean(p[m:len(stacks)])
    return out


def terminal_stacks(spot: Spot, pusher: int | None, caller: int | None = None,
                    winner: int | None = None) -> np.ndarray:
    """Stacks after: walk (pusher None), steal (no caller) or showdown won by `winner`."""
    s = np.asarray(spot.stacks, dtype=float)
    out = s - spot.posts
    total = spot.posts.sum()
    if pusher is None:
        out[-1] += total
        return out
    if caller is None:
        out[pusher] += total
        return out
    behind = s - spot.dead
    m = min(behind[pusher], behind[caller])
    out[pusher] = behind[pusher] - m
    out[caller] = behind[caller] - m
    others = [i for i in range(spot.n) if i not in (pusher, caller)]
    out[winner] += spot.dead.sum() + spot.blinds[others].sum() + 2 * m
    return out


@dataclass
class Strategy:
    """push[p, h]: P(seat p moves all-in first-in with class h), p < n-1.
    call[q, p, h]: P(seat q calls p's all-in with class h), q > p. Other entries unused."""
    push: np.ndarray
    call: np.ndarray

    @classmethod
    def uniform(cls, n: int, value: float = 0.5) -> "Strategy":
        return cls(np.full((n - 1, N_CLASSES), value), np.full((n, n, N_CLASSES), value))

    def copy(self) -> "Strategy":
        return Strategy(self.push.copy(), self.call.copy())


@dataclass
class Evaluation:
    value: np.ndarray                      # game value per seat ($)
    push_ev: dict[int, tuple[np.ndarray, float]] = field(default_factory=dict)   # p -> (EV push per h, EV fold)
    call_ev: dict[tuple[int, int], tuple[np.ndarray, float, np.ndarray]] = field(default_factory=dict)
    # (q, p) -> (EV call per j, EV fold, probability mass of reaching with j)
    push_reach: dict[int, float] = field(default_factory=dict)

    def gains(self, strat: Strategy, n: int) -> np.ndarray:
        """Best-response gain per seat ($), holding the others' strategies fixed."""
        g = np.zeros(n)
        for p, (ev, fold) in self.push_ev.items():
            cur = strat.push[p] * ev + (1 - strat.push[p]) * fold
            g[p] += self.push_reach[p] * PRIOR @ (np.maximum(ev, fold) - cur)
        for (q, p), (ev, fold, mass) in self.call_ev.items():
            cur = strat.call[q, p] * ev + (1 - strat.call[q, p]) * fold
            g[q] += mass @ (np.maximum(ev, fold) - cur)
        return g

    def best_response(self, strat: Strategy) -> Strategy:
        br = strat.copy()
        for p, (ev, fold) in self.push_ev.items():
            br.push[p] = np.where(ev > fold, 1.0, np.where(ev < fold, 0.0, strat.push[p]))
        for (q, p), (ev, fold, mass) in self.call_ev.items():
            br.call[q, p] = np.where(mass > 0, np.where(ev > fold, 1.0, np.where(ev < fold, 0.0, strat.call[q, p])),
                                     strat.call[q, p])
        return br


class _Tree:
    """Terminal values of a spot and the backward induction over a strategy."""

    def __init__(self, spot: Spot, value_fn: Callable[[np.ndarray], np.ndarray]):
        self.spot = spot
        n = spot.n
        self.E, Npairs = load_equity()
        self.N = Npairs
        self.Nrow = Npairs / Npairs.sum(axis=1, keepdims=True)
        self.walk = value_fn(terminal_stacks(spot, None))
        self.steal = {p: value_fn(terminal_stacks(spot, p)) for p in range(n - 1)}
        self.win = {}
        self.lose = {}
        for p in range(n - 1):
            for q in range(p + 1, n):
                self.win[p, q] = value_fn(terminal_stacks(spot, p, q, p))
                self.lose[p, q] = value_fn(terminal_stacks(spot, p, q, q))

    def evaluate(self, st: Strategy) -> Evaluation:
        n = self.spot.n
        E, N = self.E, self.N
        ev = Evaluation(value=np.zeros(n))
        sub = {}
        for p in range(n - 1):
            c = {q: self.Nrow @ st.call[q, p] for q in range(p + 1, n)}
            V = np.tile(self.steal[p], (N_CLASSES, 1))
            starts = {n: V}
            for q in range(n - 1, p, -1):
                wq = N * st.call[q, p][None, :]
                den = wq.sum(axis=1)
                e = np.divide((wq * E).sum(axis=1), den, out=np.full(N_CLASSES, 0.5), where=den > 0)
                show = e[:, None] * self.win[p, q] + (1 - e)[:, None] * self.lose[p, q]
                V = (1 - c[q])[:, None] * V + c[q][:, None] * show
                starts[q] = V
            sub[p] = starts[p + 1]
            reach = np.ones(N_CLASSES)
            for q in range(p + 1, n):
                w = st.push[p] * reach
                W = N * w[None, :]
                den = W.sum(axis=1)
                evc = np.divide((W * (E * self.lose[p, q][q] + (1 - E) * self.win[p, q][q])).sum(axis=1),
                                den, out=np.zeros(N_CLASSES), where=den > 0)
                fw = PRIOR * w
                fold = float(fw @ starts[q + 1][:, q] / fw.sum()) if fw.sum() > 0 else 0.0
                ev.call_ev[q, p] = (evc, fold, den / N.sum())
                reach = reach * (1 - c[q])
        U = self.walk
        for p in range(n - 2, -1, -1):
            pw = PRIOR * st.push[p]
            ev.push_ev[p] = (sub[p][:, p], float(U[p]))
            U = pw @ sub[p] + (1 - pw.sum()) * U
        ev.value = U
        r = 1.0
        for p in range(n - 1):
            ev.push_reach[p] = r
            r *= 1 - PRIOR @ st.push[p]
        for (q, p), (evc, fold, mass) in list(ev.call_ev.items()):
            ev.call_ev[q, p] = (evc, fold, mass * ev.push_reach[p])
        return ev


@dataclass
class Solution:
    spot: Spot
    strategy: Strategy
    value: np.ndarray
    gains: np.ndarray
    iterations: int
    converged: bool

    def push_range(self, seat: int) -> dict[str, float]:
        return dict(zip(HAND_CLASSES, self.strategy.push[seat].tolist()))

    def call_range(self, seat: int, pusher: int) -> dict[str, float]:
        return dict(zip(HAND_CLASSES, self.strategy.call[seat, pusher].tolist()))

    def push_freq(self, seat: int) -> float:
        return float(PRIOR @ self.strategy.push[seat])

    def call_freq(self, seat: int, pusher: int) -> float:
        return float(PRIOR @ self.strategy.call[seat, pusher])


def _value_fn(spot: Spot, value_model: str, fgs_depth: int, tol: float, max_iter: int):
    if value_model not in VALUE_MODELS:
        raise SpotError(f"value_model must be one of {VALUE_MODELS}.")
    if value_model == "chipev":
        return lambda stacks: np.asarray(stacks, dtype=float)
    if fgs_depth <= 0:
        return lambda stacks: _place_values(stacks, spot.payouts)

    def fgs(stacks):
        base = _place_values(stacks, spot.payouts)
        live = np.flatnonzero(stacks > 0)
        if live.size < 2:
            return base
        order = np.roll(live, -1)  # next hand: everyone moves one seat toward the blinds
        try:
            nxt = Spot(tuple(int(round(stacks[i])) for i in order), spot.sb, spot.bb,
                       spot.payouts[: live.size], spot.ante, spot.bb_ante)
        except SpotError:
            return base
        sol = solve(nxt, "icm", fgs_depth - 1, tol, max_iter)
        out = base.copy()
        out[order] = sol.value
        return out

    cache: dict[tuple, np.ndarray] = {}

    def cached(stacks):
        key = tuple(np.round(stacks, 6))
        if key not in cache:
            cache[key] = fgs(np.asarray(stacks, dtype=float))
        return cache[key]
    return cached


def _scale(spot: Spot, value_model: str) -> float:
    return float(sum(spot.stacks)) if value_model == "chipev" else spot.prize_pool


def _solve_tree(tree: _Tree, scale: float, tol: float, max_iter: int) -> Solution:
    spot = tree.spot
    st = Strategy.uniform(spot.n)
    gains = np.full(spot.n, np.inf)
    for it in range(1, max_iter + 1):
        ev = tree.evaluate(st)
        gains = ev.gains(st, spot.n)
        if gains.max() <= tol * scale:
            return Solution(spot, st, ev.value, gains, it, True)
        br = ev.best_response(st)
        a = 1.0 / (it + 1)
        st = Strategy(st.push + a * (br.push - st.push), st.call + a * (br.call - st.call))
    ev = tree.evaluate(st)
    return Solution(spot, st, ev.value, ev.gains(st, spot.n), max_iter, False)


def solve(spot: Spot, value_model: str = "icm", fgs_depth: int = 0, tol: float = 1e-3,
          max_iter: int = 5000) -> Solution:
    """Approximate equilibrium; `tol` is the per-seat best-response gain bound as a fraction
    of the prize pool (of total chips for chipev)."""
    tree = _Tree(spot, _value_fn(spot, value_model, fgs_depth, tol, max_iter))
    return _solve_tree(tree, _scale(spot, value_model), tol, max_iter)


def top_percent_strategy(n: int, push_pct: float | Sequence[float],
                         call_pct: float | Sequence[float]) -> Strategy:
    """A simple non-Nash profile: push the top x of hands, call with the top y (fractions).
    Per-seat sequences are allowed; call_pct applies to every pusher."""
    top = np.array([class_top_pct()[c] for c in HAND_CLASSES])
    pp = np.broadcast_to(np.asarray(push_pct, dtype=float), (n - 1,))
    cp = np.broadcast_to(np.asarray(call_pct, dtype=float), (n,))
    push = (top[None, :] <= pp[:, None]).astype(float)
    call = np.broadcast_to((top[None, :] <= cp[:, None]).astype(float)[:, None, :], (n, n, N_CLASSES)).copy()
    return Strategy(push, call)


PolicyFn = Callable[[Spot, int, "int | None"], np.ndarray]


def evaluate_spot(policy_fn: PolicyFn, spot: Spot, opponents: Strategy | Solution, hero: int,
                  value_model: str = "icm", fgs_depth: int = 0) -> dict:
    """Hero's expected prize when `policy_fn` plays hero's decisions and `opponents` the rest.

    `policy_fn(spot, hero, pusher)` returns 169 probabilities (HAND_CLASSES order) of the
    aggressive action: push when `pusher` is None, otherwise call `pusher`'s all-in.
    Returns ev, best_response_ev (hero's best response to the same opponents), loss and
    the prize pool, all in payout units.
    """
    if not 0 <= hero < spot.n:
        raise SpotError(f"hero seat {hero} outside 0..{spot.n - 1}.")
    base = opponents.strategy if isinstance(opponents, Solution) else opponents
    st = base.copy()
    if hero < spot.n - 1:
        st.push[hero] = _policy(policy_fn, spot, hero, None)
    for p in range(hero):
        st.call[hero, p] = _policy(policy_fn, spot, hero, p)
    tree = _Tree(spot, _value_fn(spot, value_model, fgs_depth, 1e-3, 5000))
    ev = tree.evaluate(st)
    hero_ev = float(ev.value[hero])
    br = hero_ev + float(ev.gains(st, spot.n)[hero])
    return {"ev": hero_ev, "best_response_ev": br, "loss": br - hero_ev, "prize_pool": spot.prize_pool}


def _policy(fn: PolicyFn, spot: Spot, seat: int, pusher: int | None) -> np.ndarray:
    a = np.asarray(fn(spot, seat, pusher), dtype=float)
    if a.shape != (N_CLASSES,) or np.any(a < 0) or np.any(a > 1):
        raise SpotError("policy_fn must return 169 probabilities in [0, 1] (HAND_CLASSES order).")
    return a
