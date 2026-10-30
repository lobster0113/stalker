"""Preflop-deviation probe for E3 (#413): does one preflop action beat the policy's own row, per hand?

LBR (`referee.e3.lbr`) values a check or call as "equity now x pot", so it cannot tell a preflop limp
from an open: both lead to a postflop it does not play. It missed the #391 leak (served policies limp
the top first-in hands 54-85% of the time). This probe asks the question directly. For each spot

    first_in  every seat before the hero folded
    vs_open   exactly one seat before the hero made a (non all-in) raise, the rest folded

and each hand group (AA, KK, AKs, ...), it deals the hero a combo of the group, plays the seats before
it with the frozen policy and keeps only the deals that reach the spot (rejection sampling, so their
cards follow the policy's ranges for that line). Then it plays each of the hero's legal first actions
to the end of the hand, with every seat - the hero included - following the frozen policy afterwards.
The public ranges move by the policy's own row for the action taken, so the other seats read the
deviation as the policy would. All actions of a deal share the deck (same board) and one random
stream: common random numbers, so the per-deal differences carry much less noise than the values.

The policy's mix is worth sum(row x EV) on each deal. A deviation's gain is EV(action) - mix on the same
deal; `open_minus_limp` is EV(raise size) - EV(call). A cell is a leak when the best deviation's gain is
more than THRESHOLD_BB and its lower confidence bound is above zero, the bound corrected for every
(cell, action) the run tests (Bonferroni), so a probe over many cells does not flag noise. The 95% CI of
each number is reported as well.

Gate L: the deviation is chosen per (spot, seat, hand group), never per deal, so it depends only on the
hero's own cards and the public line. The policy is read with the training keys and public ranges
(`seat_probs`); other seats' hole cards only drive their own policy draws and the showdown.

The result is a found exploitation gain at one decision - a lower bound, like LBR (GATES.md Q3), never
a certificate. Local runs are reference values only (CLAUDE.md).

    python -m referee.e3.preflop_probe web/app/policy/mid-6.json --deals 300 --workers 4
"""
from __future__ import annotations

import argparse
import json
import sys
from multiprocessing import Pool
from pathlib import Path
from statistics import NormalDist

import numpy as np

from referee.e3.lbr import seat_probs
from stalker.core.cards import COMBOS, RANKS, hand_class
from stalker.e2.eq_view import combo_index
from stalker.e3 import game as G
from stalker.e3 import tp_key as K

SPOTS = ("first_in", "vs_open")
# The #391 table: the merged top steps hold pairs and big aces; these are the hands a sane preflop
# never limps or folds first in, so a gain there is a leak and not a close mixed decision.
GROUPS = ("AA", "KK", "QQ", "JJ", "TT", "AKs", "AKo", "AQs", "AQo", "AJs", "KQs")
# Pre-registered before the first run on a served policy (#413). Half a big blind per hand at one
# decision is above the whole-table LBR noise (mid 0.135 +- 0.21 bb/hand) yet far below
# the #391 AA gap (+2.5bb), so a flag means a real, large leak.
THRESHOLD_BB = 0.5
ALPHA = 0.05            # family-wise, one-sided, over every (cell, action) of a run
Z95 = 1.959964
CHUNK = 50              # deals per task; chunk seeds depend only on the cell and its index, not on workers
MAX_TRIES = 400         # rejection attempts per wanted deal before the cell gives up (unreachable spot)


def load(path: Path) -> dict:
    """A web policy file (`stalker.web.policy`, stalker/tools/export_web_policy.py) as a probe table."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if d.get("schema") != "stalker.web.policy":
        raise SystemExit(f"{path}: not a web policy file (schema stalker.web.policy); export one with "
                         "python -m stalker.tools.export_web_policy")
    q = d["q"]
    return {"policy": {k: [x / q for x in v] for k, v in d["policy"].items()}, "k": d["k"], "depth": d["depth"],
            "players": d["players"], "menu": d.get("menu", "v1"), "raise_cap": d.get("raise_cap", G.RAISE_CAP)}


def group_combos(name: str) -> list[tuple[int, int]]:
    """Every combo of a 169-class name ("AA", "AKs", "T9o")."""
    if len(name) not in (2, 3) or name[0] not in RANKS or name[1] not in RANKS:
        raise ValueError(f"{name!r}: a hand group is a 169-class name such as AA, AKs or T9o")
    out = [c for c in COMBOS if hand_class(*c) == name]
    if not out:
        raise ValueError(f"{name!r}: no combo has that class")
    return out


def _deal(rng, t: dict, seat: int, mine: tuple[int, int]) -> G.State:
    n = t["players"]
    rest = [int(c) for c in rng.permutation([c for c in range(52) if c not in mine])]
    hole = [tuple(rest[2 * i:2 * i + 2]) for i in range(n - 1)]
    hole.insert(seat, mine)
    s = G.deal(rng, n, t["menu"], t["raise_cap"])
    return s._replace(hole=tuple(hole), deck=tuple(rest[2 * (n - 1):]))


def _reach(t: dict, s: G.State, seat: int, spot: str, rng):
    """Play the seats before `seat` with the policy; (state, ranges) if the line is `spot`, else None."""
    pol, k, depth = t["policy"], t["k"], t["depth"]
    ranges = K.initial_ranges(s.n)
    opened = False
    while s.to_act != seat:
        q = s.to_act
        acts = G.legal(s)
        pr = seat_probs(pol, s, q, ranges, k, depth)
        row = pr[combo_index(s.hole[q])]
        i = int(rng.choice(len(acts), p=row / row.sum()))
        a = acts[i]
        if a != "f" and (spot == "first_in" or opened or a not in G.SIZE_LABELS):
            return None              # a limp, a second raise or an all-in: not this spot
        opened = opened or a != "f"
        ranges = K.update_range(ranges, q, pr[:, i])
        s = G.apply(s, a)
        if s.done:
            return None
    if spot == "vs_open" and not opened:
        return None
    return s, ranges


def _playout(t: dict, s: G.State, ranges, rng) -> G.State:
    pol, k, depth = t["policy"], t["k"], t["depth"]
    while not s.done:
        q = s.to_act
        pr = seat_probs(pol, s, q, ranges, k, depth)
        row = pr[combo_index(s.hole[q])]
        i = int(rng.choice(len(row), p=row / row.sum()))
        ranges = K.update_range(ranges, q, pr[:, i])
        s = G.apply(s, G.legal(s)[i])
    return s


def deals(t: dict, spot: str, seat: int, group: str, count: int, seed) -> tuple[list, int]:
    """Up to `count` deals that reach `spot` for `seat` holding `group`: (actions, the policy's row, EV per
    action in bb) each, and the number of rejection attempts."""
    rng = np.random.default_rng(seed)
    pool = group_combos(group)
    pol, k, depth = t["policy"], t["k"], t["depth"]
    out, tries = [], 0
    while len(out) < count and tries < MAX_TRIES * count:
        tries += 1
        s = _deal(rng, t, seat, pool[int(rng.integers(len(pool)))])
        got = _reach(t, s, seat, spot, rng)
        if got is None:
            continue
        s, ranges = got
        acts = G.legal(s)
        pr = seat_probs(pol, s, seat, ranges, k, depth)
        row = pr[combo_index(s.hole[seat])]
        stream = int(rng.integers(1 << 62))
        vals = []
        for i, a in enumerate(acts):
            end = _playout(t, G.apply(s, a), K.update_range(ranges, seat, pr[:, i]), np.random.default_rng(stream))
            vals.append(float(G.payoff(end)[seat]) / G.BB)
        out.append((tuple(acts), (row / row.sum()).tolist(), vals))
    return out, tries


_T: dict | None = None


def _init(t: dict) -> None:
    global _T
    _T = t


def _task(args) -> tuple[list, int]:
    spot, seat, group, count, seed = args
    return deals(_T, spot, seat, group, count, seed)


def _mean_se(x: np.ndarray) -> tuple[float, float]:
    return float(x.mean()), float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else float("inf")


def _ci(m: float, se: float, z: float = Z95) -> list[float]:
    return [round(m - z * se, 4), round(m + z * se, 4)]


def summarize(spot: str, seat: int, group: str, res: list, tries: int, n: int) -> dict:
    """One cell's numbers. Actions are compared only on deals where they were legal (the menu can drop
    a size near all in); the mix is always the row over that deal's legal actions."""
    cell = {"spot": spot, "seat": G.position_names(n)[seat], "group": group, "deals": len(res),
            "reach": round(len(res) / tries, 4) if tries else 0.0}
    if len(res) < 2:
        return cell | {"actions": {}, "best": None, "leak": False}
    labels = list(dict.fromkeys(a for acts, _, _ in res for a in acts))
    per = {}
    for a in labels:
        ev, gap, freq = [], [], []
        for acts, row, vals in res:
            if a in acts:
                i = acts.index(a)
                mix = float(np.dot(row, vals))
                ev.append(vals[i])
                gap.append(vals[i] - mix)
                freq.append(row[i])
        if len(ev) < 2:
            continue
        m, se = _mean_se(np.array(ev))
        g, gse = _mean_se(np.array(gap))
        per[a] = {"row": round(float(np.mean(freq)), 4), "ev_bb": round(m, 4), "ev_ci": _ci(m, se),
                  "vs_row_bb": round(g, 4), "vs_row_se": round(gse, 4), "vs_row_ci": _ci(g, gse)}
    olimp = {}
    for a in labels:
        if a not in G.SIZE_LABELS:
            continue
        d = [vals[acts.index(a)] - vals[acts.index("c")] for acts, _, vals in res if a in acts and "c" in acts]
        if len(d) >= 2:
            m, se = _mean_se(np.array(d))
            olimp[a] = {"bb": round(m, 4), "ci": _ci(m, se)}
    best = max(per, key=lambda a: per[a]["vs_row_bb"]) if per else None
    return cell | {"actions": per, "open_minus_limp": olimp, "best": best, "leak": False}


def flag(cells: list[dict], threshold: float = THRESHOLD_BB, alpha: float = ALPHA) -> float:
    """Mark the leaks in place; returns the corrected z used for the lower bound."""
    tests = sum(len(c["actions"]) for c in cells)
    z = NormalDist().inv_cdf(1 - alpha / max(tests, 1))
    for c in cells:
        b = c.get("best")
        if b is None:
            continue
        x = c["actions"][b]
        low = x["vs_row_bb"] - z * x["vs_row_se"]
        c["leak_low_bb"] = round(low, 4)
        c["leak"] = bool(x["vs_row_bb"] > threshold and low > 0)
    return z


def probe(t: dict, deals_per_cell: int = 200, seed: int = 0, spots=SPOTS, seats=None, groups=GROUPS,
          workers: int = 1, threshold: float = THRESHOLD_BB) -> dict:
    """Every (spot, seat, group) cell; seats default to every seat that can be in the spot."""
    n = t["players"]
    cells_spec = []
    for si, spot in enumerate(spots):
        if spot not in SPOTS:
            raise ValueError(f"spot {spot!r}; known: {SPOTS}")
        # The big blind is never first in; the first seat never faces an open.
        ok = range(n - 1) if spot == "first_in" else range(1, n)
        for seat in (ok if seats is None else [q for q in seats if q in ok]):
            for gi, group in enumerate(groups):
                cells_spec.append((spot, seat, group, si, gi))
    jobs, owner = [], []
    for ci, (spot, seat, group, si, gi) in enumerate(cells_spec):
        for j, start in enumerate(range(0, deals_per_cell, CHUNK)):
            ss = np.random.SeedSequence([seed, si, seat, gi, j])
            jobs.append((spot, seat, group, min(CHUNK, deals_per_cell - start), ss))
            owner.append(ci)
    if workers > 1:
        with Pool(workers, initializer=_init, initargs=(t,)) as p:
            parts = p.map(_task, jobs)
    else:
        _init(t)
        parts = [_task(j) for j in jobs]
    res = [([], 0) for _ in cells_spec]
    for ci, (r, tries) in zip(owner, parts):
        res[ci] = (res[ci][0] + r, res[ci][1] + tries)
    cells = [summarize(spot, seat, group, r, tries, n) for (spot, seat, group, _, _), (r, tries) in zip(cells_spec, res)]
    z = flag(cells, threshold)
    leaks = [c for c in cells if c["leak"]]
    return {"probe": "e3_preflop_v1", "deals_per_cell": deals_per_cell, "seed": seed, "threshold_bb": threshold,
            "alpha": ALPHA, "z_corrected": round(z, 3), "players": n, "menu": t["menu"], "k": t["k"],
            "depth": t["depth"], "cells": cells, "leaks": len(leaks),
            "leak_cells": [f"{c['spot']} {c['seat']} {c['group']}: {c['best']} +{c['actions'][c['best']]['vs_row_bb']}bb"
                           for c in leaks]}


def table(r: dict) -> str:
    lines = [f"{'spot':9} {'seat':4} {'group':5} {'deals':>5}  row (action: freq)                best  vs row bb [95% CI]          open-limp bb [95% CI]  leak"]
    for c in r["cells"]:
        if not c["actions"]:
            lines.append(f"{c['spot']:9} {c['seat']:4} {c['group']:5} {c['deals']:>5}  (spot not reached)")
            continue
        row = " ".join(f"{a}:{x['row']:.2f}" for a, x in c["actions"].items())
        b = c["actions"][c["best"]]
        ol = " ".join(f"{a}:{x['bb']:+.2f} [{x['ci'][0]:+.2f}, {x['ci'][1]:+.2f}]" for a, x in c["open_minus_limp"].items())
        lines.append(f"{c['spot']:9} {c['seat']:4} {c['group']:5} {c['deals']:>5}  {row:33} {c['best']:5} "
                     f"{b['vs_row_bb']:+6.2f} [{b['vs_row_ci'][0]:+.2f}, {b['vs_row_ci'][1]:+.2f}]   {ol:22}  "
                     f"{'LEAK' if c['leak'] else ''}")
    lines.append(f"leaks: {r['leaks']} (gain > {r['threshold_bb']}bb and Bonferroni lower bound > 0, z={r['z_corrected']})")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="E3 preflop-deviation probe (#413): EV of each first action vs the policy's row")
    ap.add_argument("policy", type=Path, help="web policy file (stalker.web.policy), e.g. web/app/policy/mid-6.json")
    ap.add_argument("--deals", type=int, default=200, help="deals per (spot, seat, group) cell")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--spots", default=",".join(SPOTS))
    ap.add_argument("--seats", default=None, help="comma-separated seat numbers (0 = UTG); default every seat")
    ap.add_argument("--groups", default=",".join(GROUPS))
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--json", type=Path, default=None, help="also write the full result here")
    ap.add_argument("--check", action="store_true", help="exit 1 when any cell is a leak")
    a = ap.parse_args(argv)
    t = load(a.policy)
    seats = None if a.seats is None else [int(x) for x in a.seats.split(",")]
    r = probe(t, a.deals, a.seed, tuple(a.spots.split(",")), seats, tuple(a.groups.split(",")), a.workers)
    r["policy"] = str(a.policy)
    print(table(r))
    if a.json:
        a.json.write_text(json.dumps(r, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 1 if a.check and r["leaks"] else 0


if __name__ == "__main__":
    sys.exit(main())
