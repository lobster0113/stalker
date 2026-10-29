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

The pro tier (`depth="pro"`, #325) is the full key plus the two items TP.md §4.1 adds for pros:

- opp.foldy: how often the opponents fold to pressure, a shrinkage estimate over the decisions where
  they faced a bet (TP.md §3: N/A below 6 such decisions). One hand never shows 6, and the base
  policy is trained in self-play where every seat is the same policy, so in this table it is always
  N/A (`fN`). The slot is kept so the key matches the TP vector and the layer-2 opponent model (ADR
  0015) can fill it from session history without a new key format.
- board.nut: heads-up, postflop only. 100 x the opponent's share of the "near-nut" mass: each public
  range's mass in the top 10% of combos by strength on this board (vs-random equity), opponent over
  both. It is public (board and public ranges only) but needs the ranges, which `public_key` does not
  receive (the protected referee evaluators call it without them), so it rides with the equity step:
  `equity_steps` returns `eq + NUT_BASE * (nut + 1)` and `key` renders it as `e<eq>|n<nut>`.
- Scale: 0-100 graded within +-3 (TP.md §4.1). A step about twice the tolerance wide gives 17 steps
  (100/17 = 5.9 points) for both hand.equity and board.nut, the same rule as the other tiers
  (beginner +-12.5 -> 5 steps, mid +-5 -> 11).

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

TIER_K = {"beginner": 5, "mid": 11, "pro": 17}
# Key depth per tier = the TP items that tier is asked (docs/TP.md §4.1: tier = depth of knowledge).
TIER_DEPTH = {"beginner": "basic", "mid": "full", "pro": "pro"}
# The step count names the tier for `equity_steps`: the referee evaluators pass it only k (#325).
K_PRO = TIER_K["pro"]
NUT_BASE = 1000                  # encoded pro step = eq + NUT_BASE * (nut + 1); eq < K_PRO < NUT_BASE
NUT_TOP = 0.10                   # board.nut: share of combos counted as near-nut (TP.md §3)
FOLDY_MIN_OPPS = 6               # opp.foldy is N/A below this many faced bets (TP.md §3)
FOLDY_PRIOR, FOLDY_PRIOR_N = 0.5, 6.0   # shrinkage toward an even fold rate, worth 6 decisions
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
    steps = quantile_buckets(np.nan_to_num(eq), live.astype(float), k)
    if k == K_PRO:
        nut = nut_step(s, seat, ranges)
        if nut is not None:
            steps = np.where(steps >= 0, steps + NUT_BASE * (nut + 1), steps)
    return steps


_UNIFORM = np.ones(N)


def board_nut(s: G.State, seat: int, ranges: list[np.ndarray]) -> float | None:
    """TP `board.nut` (0 me - 100 opponent): heads-up postflop only, else None. Public inputs only."""
    live = s.live()
    if s.street == 0 or len(live) != 2:
        return None
    opp = live[0] if live[1] == seat else live[1]
    strength = _equity_cached(tuple(s.board), _UNIFORM)
    ok = ~np.isnan(strength)
    top = ok & (strength >= np.quantile(strength[ok], 1 - NUT_TOP))
    share = []
    for q in (seat, opp):
        w = ranges[q] * ok
        share.append(float((w * top).sum() / w.sum()) if w.sum() > 0 else 0.0)
    total = share[0] + share[1]
    return 50.0 if total <= 0 else 100.0 * share[1] / total


def scale_step(v: float, k: int) -> int:
    """A 0-100 value on the tier's k-step grid (pro: 6-point bins, 17 steps)."""
    return min(int(v * k / 100.0 + 1e-9), k - 1)


def nut_step(s: G.State, seat: int, ranges: list[np.ndarray]) -> int | None:
    v = board_nut(s, seat, ranges)
    return None if v is None else scale_step(v, K_PRO)


def foldy_step(folds: int = 0, opportunities: int = 0) -> str:
    """TP `opp.foldy` on the pro grid from session counts; "N" (N/A) below FOLDY_MIN_OPPS faced bets."""
    if opportunities < FOLDY_MIN_OPPS:
        return "N"
    rate = (folds + FOLDY_PRIOR * FOLDY_PRIOR_N) / (opportunities + FOLDY_PRIOR_N)
    return str(scale_step(100.0 * rate, K_PRO))


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
    full = (f"{seat}|{s.street}|{n_opp}|{raise_level(s)}|{initiative(s, seat)}|"
            f"{pot_odds_step(s, seat)}|{spr_step(s, seat)}|{legal}")
    # Pro: a single hand never has the 6 faced bets opp.foldy needs, so it is N/A here (module doc).
    return f"p|{full}|f{foldy_step()}" if depth == "pro" else full


def key(public: str, step: int) -> str:
    if step >= NUT_BASE:  # pro, heads-up postflop: equity step and board.nut step
        return f"{public}|e{step % NUT_BASE}|n{step // NUT_BASE - 1}"
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
    pro:   full, with every heads-up postflop key (call keys included) also carrying one of K_PRO
           board.nut steps (opp.foldy is always N/A in this table).
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
            hu = K_PRO if depth == "pro" else 1  # n_opp = 1 of the 3 n_opp values
            total += n * (2 + hu) * 4 * 3 * po * (len(SPR_EDGES) + 1) * legal
        hu = K_PRO if depth == "pro" and street > 0 else 1
        total += (2 + hu) * po * len(LEGAL_CALL)
    return total * k


def update_range(ranges: list[np.ndarray], seat: int, action_probs: np.ndarray) -> list[np.ndarray]:
    """Bayes update after `seat` acts: its range times its probability of that action per combo.
    The other seats keep the same array objects (the equity cache keys on them)."""
    out = list(ranges)
    out[seat] = ranges[seat] * action_probs
    return out


def my_step(steps: np.ndarray, s: G.State, seat: int) -> int:
    return int(steps[combo_index(s.hole[seat])])
