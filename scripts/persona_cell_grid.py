"""Joint grid for the fish personas' flop cell levers against the mixed-field guards (#730, follow-up of #722).

Usage: python scripts/persona_cell_grid.py [--points N] [--workers W] [--hands H] [--sample-seed S] [--base-only]
           [--grid TYPE:LEVER=v1,v2,...]...
One JSON line per point: levers, turn/river fold error, per-type river mean, worst seat WTSD deviation, cell
measurements and `passed`. The guards are the ones of tests/test_persona_v2.py::test_street_style_within_6pp_of_target_in_mixed_field
(same three 6-max tables, seeds and hands); their values are constants here and must not be loosened to make a point pass.
"""
from __future__ import annotations

import argparse
import dataclasses
import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from stalker.agents.persona import PRESETS_V2, PersonaAgent
from stalker.agents.persona_stats import CELLS as FLOP_CELLS, measure_session

TYPES = list(PRESETS_V2)
TABLES = [TYPES[:6], TYPES[2:8], TYPES[:2] + TYPES[4:8]]
# note §9 target WTSD (docs/research/2026-10-30-population-stats.md), same as the test
WTSD = dict(zip(TYPES, (0.21, 0.23, 0.27, 0.28, 0.33, 0.40, 0.35, 0.28)))
TURN_ERR, RIVER_ERR, RIVER_CAP, TURN_CAP, TOL, FIDELITY_TOL = 0.14, 0.22, 0.80, 0.95, 0.06, 0.05
LOOSE, TIGHT = ("calling_station", "maniac", "loose_passive"), ("nit", "weak_tight", "tag", "lag", "pro")
# (cbet_flop, cbet_flop_mw_mult, cbet_flop_3bp_mult, fold_cbet_flop, fold_cbet_flop_mw): the #722 body's start values
CELLS = {
    "loose_passive": dict(cbet_flop=0.46, cbet_flop_mw_mult=0.83, cbet_flop_3bp_mult=1.09, fold_cbet_flop=0.34, fold_cbet_flop_mw=0.44),
    "calling_station": dict(cbet_flop=0.40, cbet_flop_mw_mult=0.82, cbet_flop_3bp_mult=1.05, fold_cbet_flop=0.23, fold_cbet_flop_mw=0.28),
}
# §10.1.6 cell targets (the 3-bet+ and multiway 3-bet+ cells have none: products of two levers)
TARGETS = {"loose_passive": {"cb_hu_srp": 0.46, "cb_mw_srp": 0.38, "f_hu_srp": 0.36, "f_mw_srp": 0.44},
           "calling_station": {"cb_hu_srp": 0.40, "cb_mw_srp": 0.34, "f_hu_srp": 0.25, "f_mw_srp": 0.30}}
MIN_OPPS = 100  # judged cells need this many pooled opportunities (the mixed field gives station multiway c-bets ~150)
LEVERS = ("giveup_weak", "giveup_turn", "probe_turn")
DEFAULT_GRID = {"giveup_weak": (0.6, 0.7), "giveup_turn": (0.3, 0.4, 0.5), "probe_turn": (0.4, 0.5)}


def evaluate(params: dict, hands: int = 20000) -> dict:
    """Judge `params` (type -> PersonaParams) like the mixed-field test does; returns the measurements and `passed`."""
    bad, seen, fold, wtsd_dev = [], set(), {}, 0.0
    opp = {n: {f"{b}_{c}": 0 for b in ("cb", "f") for c in FLOP_CELLS} for n in CELLS}
    hit = {n: dict(d) for n, d in opp.items()}
    for gi, grp in enumerate(TABLES):
        ss = np.random.SeedSequence(gi).spawn(6)
        agents = [PersonaAgent(params[n], np.random.default_rng(s)) for n, s in zip(grp, ss)]
        for n, st in zip(grp, measure_session(agents, hands, seed=50 + gi)):
            p = params[n]
            has_cells = p.cbet_flop_mw_mult is not None  # a cell persona's mixed total is not a target (#670)
            for key, tgt in () if has_cells else (("cbet_flop", p.cbet_flop), ("fold_cbet_flop", p.fold_cbet_flop)):
                got = getattr(st, key)
                seen.add((n, key))
                if got is None or abs(got - tgt) > TOL:
                    bad.append(f"{n} {key}")
            for key in ("vpip", "pfr"):
                if abs(getattr(st, key) - getattr(p, key)) > FIDELITY_TOL:
                    bad.append(f"{n} {key}")
            fold.setdefault(n, []).append((st.fold_cbet_turn, st.fold_river))
            seen.add((n, "wtsd"))
            if st.wtsd is None or abs(st.wtsd - WTSD[n]) > TOL:
                bad.append(f"{n} wtsd")
            if st.wtsd is not None:
                wtsd_dev = max(wtsd_dev, abs(st.wtsd - WTSD[n]))
            if n in CELLS:  # pooled over this type's seats, as tests/test_persona_v2.py::_pooled_cells
                for c, v in st.flop_cells.items():
                    opp[n][f"cb_{c}"] += v.cbet_opps
                    hit[n][f"cb_{c}"] += round((v.cbet or 0) * v.cbet_opps)
                    opp[n][f"f_{c}"] += v.fold_opps
                    hit[n][f"f_{c}"] += round((v.fold_cbet or 0) * v.fold_opps)
    mean = {n: tuple(float(np.mean([f[i] for f in v if f[i] is not None])) for i in (0, 1)) for n, v in fold.items()}
    for i, (street, cap) in enumerate((("turn", TURN_CAP), ("river", RIVER_CAP))):
        if not max(mean[n][i] for n in LOOSE) < min(mean[n][i] for n in TIGHT):
            bad.append(f"{street} loose<tight order")
        if not max(m[i] for m in mean.values()) < cap:
            bad.append(f"{street} cap {cap}")
    cells = {n: {k: [round(hit[n][k] / opp[n][k], 4) if opp[n][k] else None, opp[n][k]] for k in opp[n]} for n in CELLS}
    for n in CELLS:
        if params[n].cbet_flop_mw_mult is None:
            continue
        for k, t in TARGETS[n].items():
            if cells[n][k][0] is None or cells[n][k][1] < MIN_OPPS or abs(cells[n][k][0] - t) > TOL:
                bad.append(f"{n} cell {k}")
    turn = float(np.mean([abs(mean[n][0] - params[n].fold_cbet_turn) for n in TYPES]))
    river = float(np.mean([abs(mean[n][1] - params[n].fold_river) for n in TYPES]))
    if turn > TURN_ERR:
        bad.append("turn err")
    if river > RIVER_ERR:
        bad.append("river err")
    # every type adds wtsd; non-cell types add cbet_flop and fold_cbet_flop too (the test's `len(seen) == 20` with tag/pro on cells)
    expect = sum(1 if params[n].cbet_flop_mw_mult is not None else 3 for n in TYPES)
    if len(seen) != expect:
        bad.append(f"seen {len(seen)} != {expect}")
    return {"turn_err": round(turn, 4), "river_err": round(river, 4),
            "river_mean": {n: round(mean[n][1], 4) for n in TYPES}, "river_max": round(max(m[1] for m in mean.values()), 4),
            "wtsd_dev_max": round(wtsd_dev, 4), "cells": cells, "violations": sorted(set(bad)), "passed": not bad}


def apply(base: dict, point: dict) -> dict:
    """point: type -> {lever: value}; returns the type -> PersonaParams with the cell levers and the point's levers on."""
    out = dict(base)
    for n, kv in point.items():
        out[n] = dataclasses.replace(out[n], **CELLS.get(n, {}), **kv)
    return out


def _run(args: tuple) -> dict:
    point, hands = args
    res = evaluate(apply(PRESETS_V2, point), hands)
    return {"levers": point, **res}


def build_points(grids: dict[str, dict[str, tuple]], n: int, seed: int) -> list[dict]:
    """All combinations over both types' grids, subsampled to at most n by a seeded draw (the start point is always kept)."""
    per_type = []
    for t, g in grids.items():
        keys = sorted(g)
        per_type.append([{t: dict(zip(keys, vals))} for vals in itertools.product(*(g[k] for k in keys))])
    full = [{k: v for d in combo for k, v in d.items()} for combo in itertools.product(*per_type)]
    start = {t: {k: getattr(PRESETS_V2[t], k) for k in LEVERS} for t in grids}
    rest = [p for p in full if p != start]
    idx = np.random.default_rng(seed).permutation(len(rest))[: max(n - 1, 0)]
    return [start] + [rest[i] for i in sorted(idx)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", type=int, default=48, help="upper bound on measured points (seeded subsample of the product)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--hands", type=int, default=20000)
    ap.add_argument("--sample-seed", type=int, default=0)
    ap.add_argument("--grid", action="append", default=[], metavar="TYPE:LEVER=v1,v2,...",
                    help="override a type's lever values (default: both fish types, %s)" % DEFAULT_GRID)
    a = ap.parse_args()
    grids = {t: {k: tuple(v) for k, v in DEFAULT_GRID.items()} for t in CELLS}
    for item in a.grid:
        head, vals = item.split("=")
        t, lever = head.split(":")
        if t not in grids or lever not in LEVERS:
            sys.exit(f"--grid {item}: type must be one of {sorted(CELLS)}, lever one of {LEVERS}")
        grids[t][lever] = tuple(float(x) for x in vals.split(","))
    pts = build_points(grids, a.points, a.sample_seed)
    with ProcessPoolExecutor(a.workers) as ex:
        for r in ex.map(_run, [(p, a.hands) for p in pts]):
            print(json.dumps(r), flush=True)


if __name__ == "__main__":
    main()
