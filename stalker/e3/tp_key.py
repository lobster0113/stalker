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
  (100/17 = 5.9 points) for hand.equity, the same rule as the other tiers (beginner +-12.5 -> 5
  steps, mid +-5 -> 11). board.nut is graded on the same scale, but the table splits it into only
  NUT_K = 5 steps (#332): at 17 it multiplied the heads-up postflop keys by 17 (87% of all pro keys at
  2x10^4 iterations, #325) and they learn from few samples each. Grading a person's answer is a TP
  matter and does not change; the table only acts the same across 20-point board.nut bins.

Key variant "b1" (#398, ADR 0019 §3.1 B1) adds the suit-aware draw and blocker items to the hand part
of the key, graded as TP.md §4.1 asks: beginner `hand.outs`; mid and pro also `hand.vuln` and `hand.block`.
They are per-combo like hand.equity, so they ride in the same encoded step (`B1_BASE`) and `key` appends
`|o<outs>v<vuln>k<block>` (`-` where the item is N/A on that street: outs and vuln on the river, all three
preflop - preflop keys stay as they are). Call-or-fold keys never carry them (TP: a call asks only
hand.equity). The bucket edges are an initial guess meant to be moved by the b1 vs plain comparison job;
the variant name keeps every earlier table, checkpoint and key as it was.

Key variants "s2" and "s2me" (#399, ADR 0019 §3.1 S) carry the stack facts of TP.md §1.1. A player's
effective stack is their stack capped by the deepest other live player who can still act (not folded, not
all in); 0 if there is none. The key adds, before the legal actions, `s<mine>` ("s2me", "mine only") or
`s<mine>:<opponents>` ("s2": the buckets the live opponents are in, deepest first - a set, so the key says
neither which seat is which nor how many share a bucket: the opponent count is already the capped n_opp field,
and a list as long as the live opponents would carry the exact count past that cap), on the TP.md §6 depth buckets (<=5 ... 60-100, 100+ BB: EFF_EDGES_BB) of the
effective stack measured on hand-start stacks (chips behind + chips put in this hand). Preflop too, where
the plain key has no stack information. The depth is measured at hand start because SPR already carries the
chips behind over the pot; on behind chips the bucket would drift with every bet and re-encode SPR. With
equal stacks every live player's depth is that stack, so at 100BB the new field is the same everywhere
and the key carries what the plain key does. The SPR field uses the same effective stack on chips behind;
with equal stacks it is exactly `spr_step`. Call-or-fold keys stay as they are (TP: a call asks only
hand.equity against the price). Training these variants deals mixed stacks (`stalker.e3.mccfr`, stacks
"sampled").

Every feature except hand.equity is public, so one key covers the same TP situation reached by
different histories — that is the "condition-insensitive" requirement (CHARTER), checked by Gate S.
Public ranges are each seat's reach probability over the 1326 combos, Bayes-updated from that
seat's own strategy at each public action (no hidden cards).
"""
from __future__ import annotations

import math
from contextlib import contextmanager

import numpy as np

from stalker.core.cards import COMBOS, N_CARDS
from stalker.e2.abstraction import quantile_buckets
from stalker.core import fast_eval
from stalker.e2.eq_view import COMBO_ARR, N, _board_dead, _flat_runouts, combo_index, equity_vs
from stalker.e3 import game as G

TIER_K = {"beginner": 5, "mid": 11, "pro": 17}
# Key depth per tier = the TP items that tier is asked (docs/TP.md §4.1: tier = depth of knowledge).
TIER_DEPTH = {"beginner": "basic", "mid": "full", "pro": "pro"}
# The step count names the tier for `equity_steps`: the referee evaluators pass it only k (#325).
K_PRO = TIER_K["pro"]
NUT_BASE = 1000                  # encoded pro step = eq + NUT_BASE * (nut + 1); eq < K_PRO < NUT_BASE
NUT_K = 5                        # board.nut steps in the pro table (module doc, #332)
NUT_TOP = 0.10                   # board.nut: share of combos counted as near-nut (TP.md §3)
FOLDY_MIN_OPPS = 6               # opp.foldy is N/A below this many faced bets (TP.md §3)
FOLDY_PRIOR, FOLDY_PRIOR_N = 0.5, 6.0   # shrinkage toward an even fold rate, worth 6 decisions
AGGRESSIVE = G.SIZE_LABELS + ("a",)   # every menu's bet/raise labels: v1, tp6 (#339), real (#382)
VARIANTS = ("", "b1", "s2", "s2me")   # key variants: "" is every table before #398
STACK_VARIANTS = ("s2", "s2me")  # #399: effective-stack depth (and SPR) in the public key; "s2me" = mine only
EFF_EDGES_BB = (5, 10, 15, 25, 40, 60, 100)   # TP.md §6 effective-stack buckets, upper edge inclusive
B1_BASE = 10_000                 # encoded b1 part = B1_BASE * (1 + code); below it eq and board.nut (<= 5999)
B1_RADIX, B1_NA, B1_NONE = 6, 4, 5   # one b1 field: buckets 0-3, N/A on this street, not asked of this tier
OUTS_EDGES = (1e-9, 15.0, 30.0)  # hand.outs buckets: none / up to 15 / up to 30 / more (0-100 scale)
VULN_EDGES = (1e-9, 20.0)        # hand.vuln buckets: none / up to 20 / more
BLOCK_EDGES = (45.0, 60.0)       # hand.block buckets: unblocking / average / blocking (50 = average hand)
OUT_GAIN = 0.10                  # a next card is an out (vulnerability) at an equity change of +-10 points (TP.md §3)
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


def effective_stack(s: G.State, seat: int, start: bool = False) -> int:
    """TP.md §1.1: `seat`'s stack capped by the deepest other live player who can still act (0 if none).
    Chips behind; `start=True` measures hand-start stacks (behind + put in this hand) - the depth bucket."""
    chips = [s.stack[i] + (s.total[i] if start else 0) for i in range(s.n)]
    cap = [chips[i] for i in s.active() if i != seat]
    return min(chips[seat], max(cap)) if cap else 0


def spr(s: G.State, seat: int) -> float:
    """TP.md §1.1 SPR: the effective stack (chips behind) over the pot."""
    return effective_stack(s, seat) / max(s.pot, 1)


def stack_bucket(chips: int) -> int:
    """TP.md §6 depth bucket of a chip count: 0 = <=5BB ... 6 = 60-100BB, 7 = 100+BB."""
    return int(np.searchsorted(EFF_EDGES_BB, chips / G.BB, side="left"))


def stack_field(s: G.State, seat: int, variant: str) -> str:
    """The #399 key field: my depth bucket, and for "s2" the set of live opponents' buckets, deepest first."""
    mine = f"s{stack_bucket(effective_stack(s, seat, start=True))}"
    if variant == "s2me":
        return mine
    opps = sorted({stack_bucket(effective_stack(s, q, start=True)) for q in s.live() if q != seat}, reverse=True)
    return mine + ":" + "".join(map(str, opps))


def spr_step_tp(s: G.State, seat: int) -> int:
    """`spr_step` on the TP.md §1.1 effective stack (all-in players do not cap it); equal for equal stacks."""
    return 0 if s.street == 0 else int(np.searchsorted(SPR_EDGES, spr(s, seat), side="right"))


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


_NEXT_CACHE: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}
_HAS_CARD = np.stack([(COMBO_ARR == c).any(axis=1) for c in range(52)])


def _next_card_eq(board: tuple[int, ...], w: np.ndarray, cards: list[int]) -> np.ndarray:
    """Row i = `equity_vs(board + (cards[i],), w)`, bit for bit, in one batch (b1 outs/vuln, #454).

    Per-card calls spent most of their time in Python between the compiled kernels (49 cards x opponents
    x nodes); here the kernels run back to back and the nan mask and divide happen once. Cached per
    (board, range object) like `_equity_cached`: siblings in a walk share the opponents' ranges.
    """
    key = (board, id(w))
    hit = _NEXT_CACHE.get(key)
    if hit is not None and hit[0] is w:
        return hit[1]
    if not fast_eval.HAVE_NUMBA:
        out = np.stack([equity_vs(board + (c,), w) for c in cards])
    else:
        wc = np.ascontiguousarray(w, dtype=np.float64)
        acc, cnt = np.zeros((len(cards), N)), np.zeros((len(cards), N))
        for i, c in enumerate(cards):
            fast_eval.equity_segments(wc, *_flat_runouts(board + (c,)), acc[i], cnt[i])
        out = np.divide(acc, cnt, out=np.full(acc.shape, 0.5), where=cnt > 0)
        out[_board_dead(board)[None, :] | _HAS_CARD[cards]] = np.nan
    if len(_NEXT_CACHE) >= 64:  # 49 x 1326 floats = ~0.5 MB each
        _NEXT_CACHE.clear()
    _NEXT_CACHE[key] = (w, out)
    return out


def _multi_eq(board: tuple[int, ...], opps: list[int], ranges: list[np.ndarray]) -> np.ndarray:
    eq = np.ones(N)
    for q in opps:
        eq = eq * _equity_cached(board, ranges[q])
    return eq


def multi_equity(s: G.State, seat: int, ranges: list[np.ndarray]) -> np.ndarray:
    """P(beat all remaining opponents) for every combo of `seat` (nan on board collisions)."""
    return _multi_eq(tuple(s.board), [q for q in s.live() if q != seat], ranges)


_ACTIVE = {"variant": ""}


@contextmanager
def using_variant(variant: str):
    """Make `equity_steps` callers that pass no variant (the referee's LBR and field) read `variant` keys."""
    if variant not in VARIANTS:
        raise ValueError(f"key variant must be one of {VARIANTS}, got {variant!r}")
    old, _ACTIVE["variant"] = _ACTIVE["variant"], variant
    try:
        yield
    finally:
        _ACTIVE["variant"] = old


def equity_steps(s: G.State, seat: int, ranges: list[np.ndarray], k: int, variant: str | None = None,
                 depth: str | None = None) -> np.ndarray:
    eq = multi_equity(s, seat, ranges)
    live = ~np.isnan(eq)
    steps = quantile_buckets(np.nan_to_num(eq), live.astype(float), k)
    if k == K_PRO:
        nut = nut_step(s, seat, ranges)
        if nut is not None:
            steps = np.where(steps >= 0, steps + NUT_BASE * (nut + 1), steps)
    variant = _ACTIVE["variant"] if variant is None else variant
    if variant == "b1" and s.street > 0:   # preflop keys stay as they are
        depth = depth or {TIER_K["beginner"]: "basic", K_PRO: "pro"}.get(k, "full")
        steps = np.where(steps >= 0, steps + B1_BASE * (1 + b1_code(s, seat, ranges, depth)), steps)
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


def hand_block(s: G.State, seat: int, ranges: list[np.ndarray]) -> np.ndarray | None:
    """TP `hand.block` (0 blocks less - 100 blocks more) for every combo of `seat`; None preflop.

    Per opponent: r(h) = near-nut mass of its public range that shares a card with h / total
    near-nut mass (near-nut = top NUT_TOP by equity vs a random hand, as in `board_nut`). Value =
    100 r / (r + mean r over the live combos), averaged over the live opponents; nan on board
    collisions. Public inputs only.
    """
    if s.street == 0:
        return None
    strength = _equity_cached(tuple(s.board), _UNIFORM)
    ok = ~np.isnan(strength)
    top = ok & (strength >= np.quantile(strength[ok], 1 - NUT_TOP))
    pair = np.array(COMBOS)
    out = []
    for q in s.live():
        if q == seat:
            continue
        m = ranges[q] * top
        total = m.sum()
        card_mass = np.zeros(N_CARDS)
        np.add.at(card_mass, pair[:, 0], m)
        np.add.at(card_mass, pair[:, 1], m)
        r = np.where(ok, (card_mass[pair[:, 0]] + card_mass[pair[:, 1]] - m) / total, np.nan) if total > 0 else np.zeros(N)
        avg = np.nanmean(np.where(ok, r, np.nan))
        den = r + avg
        out.append(np.where(den > 0, 100.0 * r / np.where(den > 0, den, 1.0), 50.0))
    if not out:
        return None
    v = np.mean(out, axis=0)
    v[~ok] = np.nan
    return v


def hand_outs_vuln(s: G.State, seat: int, ranges: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray] | None:
    """TP `hand.outs` and `hand.vuln` (0-100) for every combo of `seat` on the flop and turn, else None.

    For each next card c: equity(c) - equity(now), with the equity of the real cards (suits count, so a
    flush draw's outs are exactly the cards of its suit; a backdoor draw is inside equity(c) because the
    runouts after c are enumerated). The cards the board, the hole cards and the opponents' public ranges
    remove are not counted; the rest are weighted by the chance no live opponent holds c. outs = share of
    weight with a gain >= +OUT_GAIN, vuln = share with a gain <= -OUT_GAIN. nan on board collisions.
    """
    board = tuple(s.board)
    if len(board) not in (3, 4):
        return None
    opps = [q for q in s.live() if q != seat]
    now = _multi_eq(board, opps, ranges)
    pair = np.array(COMBOS)
    free = np.ones(N_CARDS)
    for q in opps:
        mass = ranges[q] * ~np.isnan(_equity_cached(board, _UNIFORM))
        by_card = np.zeros(N_CARDS)
        np.add.at(by_card, pair[:, 0], mass)
        np.add.at(by_card, pair[:, 1], mass)
        free = free * (1.0 - by_card / mass.sum() if mass.sum() > 0 else 1.0)
    cards = [c for c in range(N_CARDS) if c not in board]
    nxt = np.ones((len(cards), N))
    for q in opps:
        nxt = nxt * _next_card_eq(board, ranges[q], cards)
    gain = nxt - now[None, :]
    w = free[cards][:, None] * ~np.isnan(gain)
    total = w.sum(axis=0)
    ok = (total > 0) & ~np.isnan(now)
    g = np.nan_to_num(gain)
    den = np.where(ok, total, 1.0)
    outs = np.where(ok, 100.0 * (w * (g >= OUT_GAIN)).sum(axis=0) / den, np.nan)
    vuln = np.where(ok, 100.0 * (w * (g <= -OUT_GAIN)).sum(axis=0) / den, np.nan)
    return outs, vuln


def b1_code(s: G.State, seat: int, ranges: list[np.ndarray], depth: str) -> np.ndarray:
    """Per combo, the b1 fields as one int: outs + R * vuln + R**2 * block (R = B1_RADIX), see the module doc."""
    na = np.full(N, B1_NA)
    ov = hand_outs_vuln(s, seat, ranges)
    blk = hand_block(s, seat, ranges)

    def bucket(v, edges, side):
        return np.where(np.isnan(v), B1_NA, np.searchsorted(edges, np.nan_to_num(v), side=side))

    outs = na if ov is None else bucket(ov[0], OUTS_EDGES, "left")
    if depth == "basic":
        return outs + B1_RADIX * B1_NONE + B1_RADIX ** 2 * B1_NONE
    vuln = na if ov is None else bucket(ov[1], VULN_EDGES, "left")
    block = na if blk is None else bucket(blk, BLOCK_EDGES, "right")
    return outs + B1_RADIX * vuln + B1_RADIX ** 2 * block


def b1_label(code: int) -> str:
    out = []
    for name, shift in (("o", 1), ("v", B1_RADIX), ("k", B1_RADIX ** 2)):
        f = code // shift % B1_RADIX
        if f != B1_NONE:
            out.append(name + ("-" if f == B1_NA else str(f)))
    return "".join(out)


def scale_step(v: float, k: int) -> int:
    """A 0-100 value on the tier's k-step grid (pro: 6-point bins, 17 steps)."""
    return min(int(v * k / 100.0 + 1e-9), k - 1)


def nut_step(s: G.State, seat: int, ranges: list[np.ndarray]) -> int | None:
    v = board_nut(s, seat, ranges)
    return None if v is None else scale_step(v, NUT_K)


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


def public_key(s: G.State, seat: int, depth: str = "full", variant: str | None = None) -> str:
    """`variant` None reads `using_variant` (the referee evaluators pass none)."""
    variant = _ACTIVE["variant"] if variant is None else variant
    n_opp = min(len(s.live()) - 1, 3)
    legal = "".join(G.legal(s))
    if legal in ("fc", "c"):
        # Call or fold only (facing an all-in or a capped raise): the TP for a call asks just
        # hand.equity against the required equity (ADR 0011 D1), so seat, raise count, initiative
        # and SPR are not part of the key. Fewer keys -> these rare spots learn from more samples.
        return f"call|{s.street}|{n_opp}|{pot_odds_step(s, seat)}|{legal}"
    stacks = variant in STACK_VARIANTS
    st = f"{stack_field(s, seat, variant)}|" if stacks else ""
    if depth == "basic":
        # Beginner TP: where am I, how many opponents, was there a raise, what does a call cost,
        # how strong is my hand. No exact seat, initiative or SPR.
        return (f"b|{position_group(s.n, seat)}|{s.street}|{min(n_opp, 2)}|{min(raise_level(s), 2)}|"
                f"{pot_odds_step(s, seat)}|{st}{legal}")
    sp = spr_step_tp(s, seat) if stacks else spr_step(s, seat)
    full = (f"{seat}|{s.street}|{n_opp}|{raise_level(s)}|{initiative(s, seat)}|"
            f"{pot_odds_step(s, seat)}|{sp}|{st}{legal}")
    # Pro: a single hand never has the 6 faced bets opp.foldy needs, so it is N/A here (module doc).
    return f"p|{full}|f{foldy_step()}" if depth == "pro" else full


def key(public: str, step: int) -> str:
    b1, step = divmod(step, B1_BASE)
    if step >= NUT_BASE:  # pro, heads-up postflop: equity step and board.nut step
        out = f"{public}|e{step % NUT_BASE}|n{step // NUT_BASE - 1}"
    else:
        out = f"{public}|e{step}"
    if b1 and not public.startswith("call|"):
        out += "|" + b1_label(b1 - 1)
    return out


# Legal-action strings a non-call key can carry (from `G.legal`): preflop the big blind's option uses
# "c" for check, postflop "k"; call-or-fold spots ("fc", "c") use the short call key instead.
LEGAL_PREFLOP = ("fcra", "fca", "cra", "ca")
LEGAL_POSTFLOP = ("fcra", "fca", "kb33b75a", "kb33a", "ka", "k")
LEGAL_CALL = ("fc", "c")


def _stack_mult(variant: str, n: int, n_opp: int, cap: int) -> int:
    """Key multiplier of the #399 stack field for one n_opp key value (the last one, `cap`, means cap or more)."""
    if variant not in STACK_VARIANTS:
        return 1
    b = len(EFF_EDGES_BB) + 1
    if variant == "s2me":
        return b
    most = n - 1 if n_opp == cap else n_opp
    return b * sum(math.comb(b, m) for m in range(1, min(most, b) + 1))   # non-empty sets of opponents' buckets


def theoretical_keys(n: int, k: int, depth: str = "full", variant: str = "") -> int:
    """Upper bound on the keys of one tier's table, call keys included (#253 review).

    full:  seat x n_opp(3) x raise(4) x initiative(3) x pot odds(5) x SPR(4) x legal, per street;
           preflop has one initiative and one SPR value.
    basic: position group(3) x n_opp(2) x raise(3) x pot odds(5) x legal, per street.
    call:  n_opp(3) x pot odds(5) x legal(2), per street.
    pro:   full, with every heads-up postflop key (call keys included) also carrying one of NUT_K
           board.nut steps (opp.foldy is always N/A in this table).
    b1:    every postflop non-call key also carries the b1 fields: outs (4 buckets + N/A) for basic,
           outs x vuln (3 + N/A) x block (3 + N/A) for the others.
    s2me:  every non-call key also carries my depth bucket (8); s2 also the set of the live opponents'
           buckets, at most as many as there are opponents (n_opp "3" / basic "2" covers that many up to n-1).
    Every key also carries one of k equity steps.
    """
    po = len(POT_ODDS_EDGES) + 2
    b1 = (len(OUTS_EDGES) + 2) if depth == "basic" else (len(OUTS_EDGES) + 2) * (len(VULN_EDGES) + 2) * (len(BLOCK_EDGES) + 2)
    total = 0
    for street in range(4):
        legal = len(LEGAL_PREFLOP if street == 0 else LEGAL_POSTFLOP)
        mult = b1 if variant == "b1" and street > 0 else 1
        if depth == "basic":
            total += sum(3 * 3 * po * legal * mult * _stack_mult(variant, n, j, 2) for j in (1, 2))
        elif street == 0:
            total += sum(n * 4 * po * legal * _stack_mult(variant, n, j, 3) for j in (1, 2, 3))
        else:
            for j in (1, 2, 3):
                hu = NUT_K if depth == "pro" and j == 1 else 1
                total += n * hu * 4 * 3 * po * (len(SPR_EDGES) + 1) * legal * mult * _stack_mult(variant, n, j, 3)
        hu = NUT_K if depth == "pro" and street > 0 else 1
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
