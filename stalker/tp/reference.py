"""Reference calculator for TP v0.1 item definitions (docs/TP.md §3).

Deliberately plain: exact enumeration, no sampling, no caching. It exists so hand-calculated
examples (`stalker/tp/spec/examples_v0_1.json`) and fast production code can be checked against
one readable implementation of each definition. Inputs are public observations plus explicit
assumptions (ranges, opponent policy) only — never hidden cards (docs/TP.md §2).

Ranges are lists of (combo, weight) with combo a 4-char string like "KsKd".
"""
from __future__ import annotations

from itertools import combinations, product

from stalker.core.cards import COMBOS, N_CARDS, cards, hand_class
from stalker.core.evaluator import evaluate
from stalker.core.icm import icm_equity

STREET_BOARD = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
OUTS_THRESHOLD = 0.10
NEAR_NUT_TOP = 0.10   # hand.block: share of live combos counted as near-nut (same as board.nut)


def parse_range(rng) -> list[tuple[tuple[int, int], float]]:
    out = []
    for combo, w in rng:
        c = tuple(cards(combo))
        if len(c) != 2 or c[0] == c[1]:
            raise ValueError(f"range combo {combo!r} must be two distinct cards like 'KsKd'")
        if w < 0:
            raise ValueError(f"range weight for {combo} must be >= 0")
        out.append((c, float(w)))
    return out


def _share(hero, opps, board) -> float:
    """Hero's share of the pot at showdown: 1 alone best, 1/k tied with k-1 others, else 0."""
    h = evaluate(list(hero) + list(board))
    best = max(evaluate(list(o) + list(board)) for o in opps)
    if h > best:
        return 1.0
    if h < best:
        return 0.0
    return 1.0 / (1 + sum(evaluate(list(o) + list(board)) == h for o in opps))


def equity(hero, board, ranges) -> dict[str, float]:
    """Exact showdown equity of `hero` against one weighted range per opponent.

    Opponent combos that collide with known cards or each other are dropped (card removal).
    Returns win (alone best), tie (tied best) and equity (expected pot share, ties split).
    """
    hero, board = tuple(hero), tuple(board)
    known = set(hero) | set(board)
    need = 5 - len(board)
    tot = win = tie = eq = 0.0
    for joint in product(*ranges):
        hands = [c for c, _ in joint]
        used = [x for h in hands for x in h]
        if known & set(used) or len(set(used)) != len(used):
            continue
        w = 1.0
        for _, wt in joint:
            w *= wt
        if w == 0:
            continue
        live = [c for c in range(N_CARDS) if c not in known and c not in used]
        runs = list(combinations(live, need))
        for run in runs:
            s = _share(hero, hands, board + run)
            tot += w
            eq += w * s
            win += w * (s == 1.0)
            tie += w * (0 < s < 1)
    if tot == 0:
        raise ValueError("no opponent holding is compatible with the known cards; check the ranges")
    return {"win": win / tot, "tie": tie / tot, "equity": eq / tot}


def range_vs_range(mine, theirs, board) -> float:
    """Average equity of my range against theirs (pairs weighted by both, colliding pairs dropped)."""
    tot = acc = 0.0
    for (h, wh), (o, wo) in product(mine, theirs):
        if wh * wo == 0 or set(h) & set(o) or (set(h) | set(o)) & set(board):
            continue
        e = equity(h, board, [[(o, 1.0)]])["equity"]
        tot += wh * wo
        acc += wh * wo * e
    if tot == 0:
        raise ValueError("ranges have no compatible pair on this board")
    return acc / tot


def board_adv(my_range, opp_range, board) -> float:
    """100 x (1 - my range's equity against the opponent range): 0 favours me, 100 the opponent."""
    return 100.0 * (1.0 - range_vs_range(my_range, opp_range, board))


def next_card_shift(hero, board, ranges) -> dict[str, float]:
    """hand.outs / hand.vuln: share of next cards that move hero equity by >= +10pp / <= -10pp.

    Each unseen card is weighted by its probability of coming next given the opponent ranges
    (a card an opponent may hold is less likely to come).
    """
    hero, board = tuple(hero), tuple(board)
    if len(board) not in (3, 4):
        raise ValueError("hand.outs/hand.vuln need a flop or turn board")
    now = equity(hero, board, ranges)["equity"]
    known = set(hero) | set(board)
    unseen = [c for c in range(N_CARDS) if c not in known]
    k = len(ranges)
    prob = {c: 0.0 for c in unseen}
    tot = 0.0
    for joint in product(*ranges):
        used = [x for h, _ in joint for x in h]
        if known & set(used) or len(set(used)) != len(used):
            continue
        w = 1.0
        for _, wt in joint:
            w *= wt
        tot += w
        free = [c for c in unseen if c not in used]
        for c in free:
            prob[c] += w / (len(unseen) - 2 * k)
    outs = vuln = 0.0
    for c, p in prob.items():
        if p == 0:
            continue
        rest = [[(h, w) for h, w in r if c not in h] for r in ranges]
        e = equity(hero, board + (c,), rest)["equity"]
        if e - now >= OUTS_THRESHOLD - 1e-12:
            outs += p
        elif e - now <= -OUTS_THRESHOLD + 1e-12:
            vuln += p
    return {"equity_now": now, "outs": 100.0 * outs / tot, "vuln": 100.0 * vuln / tot}


def river_strength(board) -> dict[tuple[int, int], int]:
    """Showdown rank of every live combo on a 5-card board; on the river it orders equity vs a random hand."""
    if len(board) != 5:
        raise ValueError("river_strength needs a 5-card board; pass `strength` for earlier streets")
    dead = set(board)
    return {c: evaluate(list(c) + list(board)) for c in map(tuple, combinations(range(N_CARDS), 2))
            if not dead & set(c)}


def hand_block(hero, board, opp_range, strength=None) -> float:
    """hand.block (0 blocks less - 100 blocks more): how many of the opponent's near-nut combos my cards remove.

    r(h) = opp near-nut mass on combos sharing a card with `h` / total near-nut mass; the value is
    100 x r(hero) / (r(hero) + r(average over all live hero holdings)), 50 = an average hand.
    Near-nut = the top NEAR_NUT_TOP of live combos by `strength` (ties at the cut stay in), default
    river showdown rank. One opponent; average per opponent for several.
    """
    hero, board = tuple(hero), tuple(board)
    strength = river_strength(board) if strength is None else {tuple(sorted(c)): v for c, v in strength.items()}
    ranked = sorted(strength.values())
    cut = ranked[min(len(ranked) - 1, int(len(ranked) * (1 - NEAR_NUT_TOP)))]
    top = {c for c, v in strength.items() if v >= cut}
    mass = {}
    for c, w in opp_range:
        c = tuple(sorted(c))
        if c in top and not set(c) & set(board):
            mass[c] = mass.get(c, 0.0) + w
    total = sum(mass.values())
    if total == 0:
        return 50.0

    def r(h):
        return sum(w for c, w in mass.items() if set(c) & set(h)) / total

    holdings = [c for c in combinations(range(N_CARDS), 2) if not set(c) & set(board)]
    avg = sum(r(h) for h in holdings) / len(holdings)
    mine = r(hero)
    return 50.0 if mine + avg == 0 else 100.0 * mine / (mine + avg)


def opp_value(bet_range, my_calling_range, board) -> float:
    """Share (0-100) of the opponent's betting range with > 50% showdown equity against my calling range.

    Semi-bluffs count as bluffs: only current showdown equity matters (definition fixed in TP v0.1).
    """
    tot = val = 0.0
    for o, w in bet_range:
        if w == 0 or set(o) & set(board):
            continue
        e = equity(o, board, [my_calling_range])["equity"]
        tot += w
        val += w * (e > 0.5)
    return 100.0 * val / tot


def fold_equity(opponents) -> float:
    """Probability (0-100) that every opponent folds to the presented size.

    `opponents` is a list of ranges of (combo, weight, fold_prob); opponents are independent.
    """
    p = 1.0
    for rng in opponents:
        tot = sum(w for _, w, _ in rng)
        p *= sum(w * f for _, w, f in rng) / tot
    return 100.0 * p


def icm_risk_premium(stacks: list[int], payouts: list[float], hero: int, villain: int,
                     pot_before_call: int, to_call: int) -> dict[str, float]:
    """plan.icm for calling an all-in: ICM required equity - chip-EV required equity, in pp.

    Stacks are after the villain's all-in and before hero's call; `pot_before_call` includes the
    shove. Hero must cover the call. A player busted by this hand finishes below everyone still
    alive (the next payout down).
    """
    if to_call > stacks[hero]:
        raise ValueError("hero must cover the call; short calls (side pots) are out of scope in v0.1")
    n = len(stacks)

    def value(st):
        alive = [i for i, s in enumerate(st) if s > 0]
        eq = icm_equity([st[i] for i in alive], payouts[:len(alive)])
        out = {i: e for i, e in zip(alive, eq)}
        place = len(alive)
        for i in range(n):
            if st[i] == 0 and stacks[i] > 0:
                out[i] = payouts[place] if place < len(payouts) else 0.0
        return out.get(hero, 0.0)

    fold = list(stacks)
    fold[villain] += pot_before_call
    win = list(stacks)
    win[hero] += pot_before_call
    lose = list(stacks)
    lose[villain] += pot_before_call + to_call
    lose[hero] -= to_call
    v_fold, v_win, v_lose = value(fold), value(win), value(lose)
    icm_req = (v_fold - v_lose) / (v_win - v_lose)
    chip_req = to_call / (pot_before_call + to_call)
    return {"icm_required": icm_req, "chip_required": chip_req, "premium_pp": 100.0 * (icm_req - chip_req)}


def _expand(classes: list[str]) -> set[str]:
    out = set()
    for c in classes:
        if c == "pairs":
            out |= {r * 2 for r in "23456789TJQKA"}
        else:
            out.add(c)
    return out


def opp_range(hero, board, policy: list[dict]) -> dict:
    """Posterior over opponent combos after one observed line, from a uniform prior.

    `policy` is a list of {"classes": [...], "freq": f}: the probability the opponent takes the
    observed line with a hand of those classes (others 0). Returns per-class UI cells — value =
    100 x mean line frequency over that class's live combos, `live` = live combo count — and the
    posterior probability of each class.
    """
    freq: dict[str, float] = {}
    for rule in policy:
        for c in _expand(rule["classes"]):
            freq[c] = float(rule["freq"])
    dead = set(hero) | set(board)
    cells: dict[str, dict] = {}
    mass: dict[str, float] = {}
    for a, b in COMBOS:
        if a in dead or b in dead:
            continue
        cls = hand_class(a, b)
        f = freq.get(cls, 0.0)
        cell = cells.setdefault(cls, {"sum": 0.0, "live": 0})
        cell["sum"] += f
        cell["live"] += 1
        mass[cls] = mass.get(cls, 0.0) + f
    total = sum(mass.values())
    if total == 0:
        raise ValueError("the policy never takes the observed line with any live hand")
    view = {c: {"value": 100.0 * v["sum"] / v["live"], "live": v["live"]} for c, v in cells.items()}
    return {"cells": view, "posterior": {c: m / total for c, m in mass.items() if m > 0}}


def not_applicable(item: str, ctx: dict, min_opportunities: dict[str, int]) -> str | None:
    """Reason the item is N/A in this decision context, or None if it applies (docs/TP.md §3)."""
    street = ctx.get("street")
    if item in min_opportunities and ctx.get("opportunities", 0) < min_opportunities[item]:
        return f"fewer than {min_opportunities[item]} opportunities"
    if item in ("board.adv", "board.nut") and (street == "preflop" or ctx.get("opponents", 1) > 1):
        return "postflop heads-up only"
    if item in ("hand.outs", "hand.vuln") and street not in ("flop", "turn"):
        return "flop or turn only"
    if item == "hand.block" and street not in ("flop", "turn", "river"):
        return "postflop only"
    if item == "opp.value" and not ctx.get("opponent_bet_this_street"):
        return "no opponent bet or raise this street"
    if item == "plan.foldeq" and not ctx.get("bet_or_raise_legal"):
        return "bet or raise not legal"
    if item == "plan.icm" and (ctx.get("game") != "tournament" or not ctx.get("call_or_all_in")):
        return "tournament call or all-in decisions only"
    if item == "opp.range" and ctx.get("opponents", 1) < 1:
        return "no opponent left"
    return None
