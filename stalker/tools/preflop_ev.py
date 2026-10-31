"""Action values at a first-in preflop spot under a policy (#391): `python -m stalker.tools.preflop_ev`.

Seat `seat` is first in (every seat before it folded) holding one hand or any combo of one equity
step. For each of its legal first actions the hand is played to the end with every seat, `seat`
included, following the policy from there on; the result is chip EV in bb per action. The seats
before it are rejection-sampled with their fold probability, so their cards follow the policy's
folding range. All actions of one deal share a random stream (common random numbers), so the
differences between actions have a much smaller error than the values themselves.

This asks the question LBR cannot answer at its noise level (#391): is the policy's row at this key
a best response to the policy itself? A row that puts most of its weight on an action worth clearly
less than another is a leak the training did not remove, whatever the reason. Monte Carlo, so
every number carries its standard error; local numbers are for reference only (CLAUDE.md).

    python -m stalker.tools.preflop_ev --policy web/app/policy/mid-6.json --seat 3 --hand AhQh --hands 4000
    python -m stalker.tools.preflop_ev --policy web/app/policy/mid-6.json --seat 3 --hand e10
"""
from __future__ import annotations

import argparse
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from referee.e3.lbr import seat_probs
from stalker.core.cards import cards
from stalker.e2.eq_view import COMBO_ARR, combo_index
from stalker.e3 import game as G
from stalker.e3 import tp_key as K

CHUNK = 50   # deals per worker task; the seed of chunk i is seed + i, so results do not depend on workers


def load(path: Path) -> dict:
    """A web service policy file (`stalker.web.policy`) as {"policy", "k", "depth", "players", "menu", "raise_cap"}."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if d.get("schema") != "stalker.web.policy":
        raise SystemExit(f"{path}: not a web policy file (stalker.web.policy); export one with stalker.tools.export_web_policy")
    q = d["q"]
    return {"policy": {k: [x / q for x in v] for k, v in d["policy"].items()}, "k": d["k"], "depth": d["depth"],
            "players": d["players"], "menu": d.get("menu", "v1"), "raise_cap": d.get("raise_cap", G.RAISE_CAP)}


def first_in(t: dict, seat: int) -> tuple[G.State, list[np.ndarray]]:
    """The public state and ranges when `seat` is first in: earlier seats folded, ranges moved by their fold rows."""
    s = G.deal(np.random.default_rng(0), t["players"], t["menu"], t["raise_cap"])  # preflop keys ignore the cards
    ranges = K.initial_ranges(t["players"])
    for q in range(seat):
        pr = seat_probs(t["policy"], s, q, ranges, t["k"], t["depth"])
        ranges = K.update_range(ranges, q, pr[:, G.legal(s).index("f")])
        s = G.apply(s, "f")
    return s, ranges


def hand_pool(t: dict, seat: int, hand: str) -> list[tuple[int, int]]:
    """`hand` as the combos `seat` may hold: one hand ("AhQh"), every combo of an equity step ("e10"), or
    every combo ("any", a random first-in hand)."""
    if hand == "any":
        return [(int(a), int(b)) for a, b in COMBO_ARR]
    if not hand.startswith("e"):
        return [tuple(cards(hand))]
    s, ranges = first_in(t, seat)
    steps = K.equity_steps(s, seat, ranges, t["k"])
    pool = [(int(a), int(b)) for a, b in COMBO_ARR[steps == int(hand[1:])]]
    if not pool:
        raise SystemExit(f"{hand}: no combo is in that step at this spot (k={t['k']})")
    return pool


def _deal(rng, n: int, seat: int, mine: tuple[int, int], t: dict) -> G.State:
    rest = [int(c) for c in rng.permutation([c for c in range(52) if c not in mine])]
    hole = [tuple(rest[2 * i:2 * i + 2]) for i in range(n - 1)]
    hole.insert(seat, mine)
    s = G.deal(rng, n, t["menu"], t["raise_cap"])
    return s._replace(hole=tuple(hole), deck=tuple(rest[2 * (n - 1):]))


def deals(t: dict, seat: int, pool: list, count: int, seed: int) -> list[tuple[int, list[float], list[float]]]:
    """`count` deals where `seat` is first in: (equity step, the policy's row for the hand, EV per action in bb)."""
    rng = np.random.default_rng(seed)
    pol, k, depth, n = t["policy"], t["k"], t["depth"], t["players"]
    out = []
    while len(out) < count:
        s = _deal(rng, n, seat, pool[int(rng.integers(len(pool)))], t)
        ranges = K.initial_ranges(n)
        folded_to = True
        for q in range(seat):
            pr = seat_probs(pol, s, q, ranges, k, depth)
            f = G.legal(s).index("f")
            if rng.random() >= pr[combo_index(s.hole[q]), f]:
                folded_to = False
                break
            ranges = K.update_range(ranges, q, pr[:, f])
            s = G.apply(s, "f")
        if not folded_to:
            continue
        acts = G.legal(s)
        probs = seat_probs(pol, s, seat, ranges, k, depth)
        me = combo_index(s.hole[seat])
        stream = int(rng.integers(1 << 62))
        vals = []
        for a in range(len(acts)):
            r2 = np.random.default_rng(stream)
            rs = K.update_range(ranges, seat, probs[:, a])
            x = G.apply(s, acts[a])
            while not x.done:
                q = x.to_act
                pr = seat_probs(pol, x, q, rs, k, depth)
                row = pr[combo_index(x.hole[q])]
                i = int(r2.choice(len(row), p=row / row.sum()))
                rs = K.update_range(rs, q, pr[:, i])
                x = G.apply(x, G.legal(x)[i])
            vals.append(float(G.payoff(x)[seat]) / G.BB)
        step = int(K.equity_steps(s, seat, ranges, k)[me])
        out.append((step, probs[me].tolist(), vals))
    return out


_T: dict | None = None


def _init(t: dict) -> None:
    global _T
    _T = t


def _chunk(args) -> list:
    seat, pool, count, seed = args
    return deals(_T, seat, pool, count, seed)


def action_values(t: dict, seat: int, hand: str = "AhQh", hands: int = 2000, seed: int = 0, workers: int = 1) -> dict:
    """EV per first action for `hand` at `seat`'s first-in spot, with standard errors, and the regret
    of the policy's row: best action's EV minus the row's EV (both against the policy)."""
    pool = hand_pool(t, seat, hand)
    jobs = [(seat, pool, min(CHUNK, hands - i), seed + i // CHUNK) for i in range(0, hands, CHUNK)]
    if workers > 1:
        with Pool(workers, initializer=_init, initargs=(t,)) as p:
            parts = p.map(_chunk, jobs)
    else:
        _init(t)
        parts = [_chunk(j) for j in jobs]
    res = [x for part in parts for x in part]
    acts = G.legal(first_in(t, seat)[0])
    v = np.array([r[2] for r in res])
    rows = np.array([r[1] for r in res])
    row_ev = (rows * v).sum(1)            # the policy's own mix, per deal
    gap = v - row_ev[:, None]             # each action against the row, same deal
    se = lambda a: float(a.std(ddof=1) / np.sqrt(len(a))) if len(a) > 1 else 0.0
    best = int(np.argmax(gap.mean(0)))
    return {"seat": G.position_names(t["players"])[seat], "hand": hand, "deals": len(res), "actions": acts,
            "row": rows.mean(0).round(4).tolist(), "ev_bb": v.mean(0).round(4).tolist(),
            "ev_se": [round(se(v[:, i]), 4) for i in range(len(acts))],
            "vs_row_bb": gap.mean(0).round(4).tolist(), "vs_row_se": [round(se(gap[:, i]), 4) for i in range(len(acts))],
            "best": acts[best], "regret_bb": round(float(gap[:, best].mean()), 4), "regret_se": round(se(gap[:, best]), 4),
            "steps": sorted({r[0] for r in res}), "by_step": _by_step(res, gap, acts)}


def _by_step(res: list, gap: np.ndarray, acts: list[str]) -> dict:
    """Per equity step: deals, the best action against the row, and the row's regret (bb per deal)."""
    steps = np.array([r[0] for r in res])
    out = {}
    for v in sorted(set(steps.tolist())):
        g = gap[steps == v].mean(0)
        out[f"e{v}"] = {"deals": int((steps == v).sum()), "best": acts[int(np.argmax(g))],
                        "regret_bb": round(float(g.max()), 4)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="EV of each first-in preflop action under a served policy (#391)")
    ap.add_argument("--policy", type=Path, required=True)
    ap.add_argument("--seat", type=int, default=3, help="0 = UTG ... (6-max: 3 = BTN, 4 = SB)")
    ap.add_argument("--hand", default="AhQh",
                    help='one hand ("AhQh"), an equity step ("e10": any combo in it) or "any" (a random hand)')
    ap.add_argument("--hands", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    t = load(a.policy)
    if not 0 <= a.seat < t["players"] - 1:
        raise SystemExit(f"--seat {a.seat}: first-in seats are 0..{t['players'] - 2} (the big blind is never first in)")
    print(json.dumps(action_values(t, a.seat, a.hand, a.hands, a.seed, a.workers)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
