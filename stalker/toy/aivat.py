"""AIVAT control-variate estimator on three-player Kuhn poker (research spike, #537).

Three players ante 1 from a 4-card deck (ranks 0..3), one betting round with bet size 1. Before any
bet `b` bets and `p` checks; after a bet `b` calls and `p` folds; each other player answers the bet
once. Every seat's strategy is a known table, which is the premise AIVAT needs (Burch et al. 2018).

The estimator subtracts, at the deal and at each decision of a seat whose strategy is known,
`v(h·sampled) - E_a[v(h·a)]`. Each term has mean zero given `h`, so the estimate stays unbiased for
any value function `v`; only the variance depends on how well `v` tracks the realised payoff, and a
poorly correlated `v` can make the variance larger. Not wired into `referee/stats.py` (out of scope).
"""
from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from functools import cache

import numpy as np

N_SEATS = 3
DECK = 4
DEALS = tuple(itertools.permutations(range(DECK), N_SEATS))
_BET_FIRST = (0.25, 0.05, 0.35, 0.9)  # bet probability by rank when nobody has bet yet
_CALL = (0.0, 0.15, 0.55, 1.0)         # call probability by rank when facing a bet

Strategy = Callable[[int, int, str], float]  # (seat, card, history) -> P(b)
Value = Callable[[tuple[int, ...], str], float]


def default_strategy(seat: int, card: int, history: str) -> float:
    # Small seat skew so the three seats are not exchangeable and corrections differ by seat.
    p = _CALL[card] if "b" in history else _BET_FIRST[card]
    return min(1.0, max(0.0, p + 0.05 * (seat - 1) * (0.0 < p < 1.0)))


def to_act(history: str) -> int | None:
    """Seat to act after `history`, or None when the hand is over."""
    if "b" not in history:
        return len(history) if len(history) < N_SEATS else None
    first = history.index("b")
    answered = len(history) - first - 1
    return (first + 1 + answered) % N_SEATS if answered < N_SEATS - 1 else None


def payoff(cards: tuple[int, ...], history: str) -> np.ndarray:
    """Net chips per seat if the hand were settled now among seats that have not folded (zero-sum)."""
    put = np.ones(N_SEATS, dtype=np.int64)
    alive = [True] * N_SEATS
    if "b" in history:
        first = history.index("b")
        put[first] += 1
        for k, a in enumerate(history[first + 1:]):
            s = (first + 1 + k) % N_SEATS
            if a == "b":
                put[s] += 1
            else:
                alive[s] = False
    winner = max((s for s in range(N_SEATS) if alive[s]), key=lambda s: cards[s])
    out = -put
    out[winner] += int(put.sum())
    return out


def exact_value(strategy: Strategy, seat: int = 0) -> Value:
    """v(h) = expected chips of `seat` from full state h under `strategy` (all cards known)."""
    @cache
    def v(cards: tuple[int, ...], history: str) -> float:
        s = to_act(history)
        if s is None:
            return float(payoff(cards, history)[seat])
        pb = strategy(s, cards[s], history)
        return pb * v(cards, history + "b") + (1.0 - pb) * v(cards, history + "p")
    return v


def showdown_value(seat: int = 0) -> Value:
    """Cheap v: settle now among seats that have not folded, with chips committed so far."""
    return lambda cards, history: float(payoff(cards, history)[seat])


def negated(v: Value) -> Value:
    """A deliberately anti-correlated v: still unbiased, but it inflates the variance."""
    return lambda cards, history: -v(cards, history)


def play(rng: np.random.Generator, strategy: Strategy) -> tuple[tuple[int, ...], str]:
    cards = DEALS[int(rng.integers(len(DEALS)))]
    h = ""
    while (s := to_act(h)) is not None:
        h += "b" if rng.random() < strategy(s, cards[s], h) else "p"
    return cards, h


def aivat(cards: tuple[int, ...], history: str, strategy: Strategy, v: Value,
          known: frozenset[int] = frozenset(range(N_SEATS)), seat: int = 0) -> float:
    """AIVAT estimate of `seat`'s chips for one played hand."""
    est = float(payoff(cards, history)[seat])
    est -= v(cards, "") - math.fsum(v(d, "") for d in DEALS) / len(DEALS)
    for i, a in enumerate(history):
        h = history[:i]
        s = to_act(h)
        if s not in known:
            continue
        pb = strategy(s, cards[s], h)
        est -= v(cards, h + a) - (pb * v(cards, h + "b") + (1.0 - pb) * v(cards, h + "p"))
    return est


def simulate(n: int, rng: np.random.Generator, strategy: Strategy = default_strategy,
             v: Value | None = None, known: frozenset[int] = frozenset(range(N_SEATS)),
             seat: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """(raw, aivat) per-hand chip results of `seat` over `n` hands."""
    v = v or exact_value(strategy, seat)
    raw = np.empty(n)
    est = np.empty(n)
    for i in range(n):
        cards, h = play(rng, strategy)
        raw[i] = payoff(cards, h)[seat]
        est[i] = aivat(cards, h, strategy, v, known, seat)
    return raw, est


def se(x: np.ndarray) -> float:
    return float(np.std(x, ddof=1) / math.sqrt(len(x)))


def true_value(strategy: Strategy = default_strategy, seat: int = 0) -> float:
    v = exact_value(strategy, seat)
    return math.fsum(v(d, "") for d in DEALS) / len(DEALS)


def table(n: int = 20000, seed: int = 0) -> list[dict]:
    """Variance-reduction rows for the research note (local reference values)."""
    rows = []
    cases = [
        ("exact v, all seats known", exact_value(default_strategy), frozenset({0, 1, 2})),
        ("exact v, seat 0 unknown", exact_value(default_strategy), frozenset({1, 2})),
        ("showdown v, all seats known", showdown_value(), frozenset({0, 1, 2})),
        ("showdown v, seat 0 unknown", showdown_value(), frozenset({1, 2})),
        ("negated showdown v, all known", negated(showdown_value()), frozenset({0, 1, 2})),
    ]
    for name, v, known in cases:
        raw, est = simulate(n, np.random.default_rng(seed), v=v, known=known)
        rows.append({"case": name, "raw_mean": float(raw.mean()), "aivat_mean": float(est.mean()),
                     "raw_se": se(raw), "aivat_se": se(est),
                     # Exact v with every seat known leaves only rounding noise (~1e-17).
                     "se_ratio": se(raw) / se(est) if se(est) > 1e-12 else math.inf})
    return rows


if __name__ == "__main__":
    print(f"true EV seat 0: {true_value():.5f}")
    for r in table():
        print(f"| {r['case']} | {r['raw_mean']:.4f} | {r['aivat_mean']:.4f} | {r['raw_se']:.4f} | "
              f"{r['aivat_se']:.4f} | {r['se_ratio']:.2f} |")
