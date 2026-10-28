"""E3-1: TP keys for N-handed play — the policy table is keyed by the TP vector, not the history (#196).

Design note #192 §3. A decision's key (full depth, `public_key` + `key`) is

    seat | street | n_opp | raise level | initiative | pot-odds step | SPR step | legal actions | e<hand.equity step>

The beginner tier (`depth="basic"`) keeps only `b | position group | street | min(n_opp, 2) |
min(raise level, 2) | pot-odds step | legal actions | e<step>`.

- n_opp: opponents still in the hand, capped at 3 ("3+").
- raise level: raises on this street (preflop the big blind does not count), capped at 3.
- initiative: who made the last bet or raise of the previous street (0 nobody / 1 me / 2 someone
  else); preflop 0.
- hand.equity: the chance to beat every remaining opponent (TP.md §3.1), approximated as the
  product of the equities against each opponent's public range (independence assumption: the
  opponents' hands are not removed from each other). Shown on a k-step quantile scale over the
  acting seat's possible combos, as in E1/E2.
- pot odds: to_call / (pot + to_call), steps 0 (nothing to call), <20%, <30%, <40%, >=40%.
- SPR: effective stack / pot, steps <1, <3, <6, >=6 (preflop: one value).

Call-or-fold-only spots (facing an all-in or a capped raise) use the short key
`call | street | n_opp | pot-odds step | legal | e<step>`: the TP for a call is equity
against the required equity.

Every feature except hand.equity is public, so one key covers the same TP situation reached by
different histories — that is the "condition-insensitive" requirement (CHARTER), checked by Gate S.
Public ranges are each seat's reach probability over the 1326 combos, Bayes-updated from that
seat's own strategy at each public action (no hidden cards).
"""
from __future__ import annotations

import numpy as np

from stalker.e2.abstraction import quantile_buckets
from stalker.e2.eq_view import N, combo_index, equity_vs
from stalker.e3 import game as G

TIER_K = {"beginner": 5, "mid": 11}
# Key depth per tier = the TP items that tier is asked (docs/TP.md §4.1: tier = depth of knowledge).
TIER_DEPTH = {"beginner": "basic", "mid": "full"}
AGGRESSIVE = ("r", "b33", "b75", "a")
POT_ODDS_EDGES = (0.2, 0.3, 0.4)
SPR_EDGES = (1.0, 3.0, 6.0)


def initial_ranges(n: int) -> list[np.ndarray]:
    return [np.ones(N) for _ in range(n)]


def _streets(history: tuple[str, ...]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for h in history:
        if h == "/":
            out.append([])
        else:
            out[-1].append(h)
    return out


def initiative(s: G.State, seat: int) -> int:
    # An all-in that only calls is also labelled "a" and counts as aggression here; that only
    # coarsens the key.
    if s.street == 0:
        return 0
    last = None
    for h in _streets(s.history)[s.street - 1]:
        p, a = h.split(":")
        if a in AGGRESSIVE:
            last = int(p)
    return 0 if last is None else 1 if last == seat else 2


def raise_level(s: G.State) -> int:
    return min(s.raises - 1 if s.street == 0 else s.raises, 3)


def pot_odds_step(s: G.State, seat: int) -> int:
    call = s.to_call(seat)
    if call <= 0:
        return 0
    ratio = call / (s.pot + call)
    return 1 + int(np.searchsorted(POT_ODDS_EDGES, ratio, side="right"))


def spr_step(s: G.State, seat: int) -> int:
    if s.street == 0:
        return 0
    others = [s.stack[i] for i in s.live() if i != seat]
    eff = min(s.stack[seat], max(others) if others else 0)
    return int(np.searchsorted(SPR_EDGES, eff / max(s.pot, 1), side="right"))


_EQ_CACHE: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}


def _equity_cached(board: tuple[int, ...], w: np.ndarray) -> np.ndarray:
    # Within a walk, seats that did not act keep the same range object, so siblings and descendants
    # reuse it; the entry holds `w` itself so its id cannot be recycled while cached.
    key = (board, id(w))
    hit = _EQ_CACHE.get(key)
    if hit is not None and hit[0] is w:
        return hit[1]
    if len(_EQ_CACHE) > 4_000:  # ~21 KB each (range + equity): ~84 MB, not ~420 MB (#253 review)
        _EQ_CACHE.clear()
    eq = equity_vs(board, w)
    _EQ_CACHE[key] = (w, eq)
    return eq


def multi_equity(s: G.State, seat: int, ranges: list[np.ndarray]) -> np.ndarray:
    """P(beat all remaining opponents) for every combo of `seat` (nan on board collisions)."""
    eq = np.ones(N)
    for q in s.live():
        if q != seat:
            eq = eq * _equity_cached(tuple(s.board), ranges[q])
    return eq


def equity_steps(s: G.State, seat: int, ranges: list[np.ndarray], k: int) -> np.ndarray:
    eq = multi_equity(s, seat, ranges)
    live = ~np.isnan(eq)
    return quantile_buckets(np.nan_to_num(eq), live.astype(float), k)


def position_group(n: int, seat: int) -> str:
    """early / late (the two seats before the blinds) / blinds."""
    if seat >= n - 2:
        return "blind"
    return "late" if seat >= n - 4 else "early"


def public_key(s: G.State, seat: int, depth: str = "full") -> str:
    n_opp = min(len(s.live()) - 1, 3)
    legal = "".join(G.legal(s))
    if legal in ("fc", "c"):
        # Call or fold only (facing an all-in or a capped raise): the TP for a call asks just
        # hand.equity against the required equity (ADR 0011 D1), so seat, raise count, initiative
        # and SPR are not part of the key. Fewer keys -> these rare spots learn from more samples.
        return f"call|{s.street}|{n_opp}|{pot_odds_step(s, seat)}|{legal}"
    if depth == "basic":
        # Beginner TP: where am I, how many opponents, was there a raise, what does a call cost,
        # how strong is my hand. No exact seat, initiative or SPR.
        return (f"b|{position_group(s.n, seat)}|{s.street}|{min(n_opp, 2)}|{min(raise_level(s), 2)}|"
                f"{pot_odds_step(s, seat)}|{legal}")
    return (f"{seat}|{s.street}|{n_opp}|{raise_level(s)}|{initiative(s, seat)}|"
            f"{pot_odds_step(s, seat)}|{spr_step(s, seat)}|{legal}")


def key(public: str, step: int) -> str:
    return f"{public}|e{step}"


# Legal-action strings a non-call key can carry (from `G.legal`): preflop the big blind's option uses
# "c" for check, postflop "k"; call-or-fold spots ("fc", "c") use the short call key instead.
LEGAL_PREFLOP = ("fcra", "fca", "cra", "ca")
LEGAL_POSTFLOP = ("fcra", "fca", "kb33b75a", "kb33a", "ka", "k")
LEGAL_CALL = ("fc", "c")


def theoretical_keys(n: int, k: int, depth: str = "full") -> int:
    """Upper bound on the keys of one tier's table, call keys included (#253 review).

    full:  seat x n_opp(3) x raise(4) x initiative(3) x pot odds(5) x SPR(4) x legal, per street;
           preflop has one initiative and one SPR value.
    basic: position group(3) x n_opp(2) x raise(3) x pot odds(5) x legal, per street.
    call:  n_opp(3) x pot odds(5) x legal(2), per street.
    Every key also carries one of k equity steps.
    """
    po = len(POT_ODDS_EDGES) + 2
    total = 0
    for street in range(4):
        legal = len(LEGAL_PREFLOP if street == 0 else LEGAL_POSTFLOP)
        if depth == "basic":
            total += 3 * 2 * 3 * po * legal
        elif street == 0:
            total += n * 3 * 4 * po * legal
        else:
            total += n * 3 * 4 * 3 * po * (len(SPR_EDGES) + 1) * legal
        total += 3 * po * len(LEGAL_CALL)
    return total * k


def update_range(ranges: list[np.ndarray], seat: int, action_probs: np.ndarray) -> list[np.ndarray]:
    """Bayes update after `seat` acts: its range times its probability of that action per combo.
    The other seats keep the same array objects (the equity cache keys on them)."""
    out = list(ranges)
    out[seat] = ranges[seat] * action_probs
    return out


def my_step(steps: np.ndarray, s: G.State, seat: int) -> int:
    return int(steps[combo_index(s.hole[seat])])
