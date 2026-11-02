"""WTSD lever sweep for PRESETS_V2 (#526): prints per-type WTSD, turn fold-to-c-bet and river fold vs. the targets.

Usage: python scripts/persona_wtsd_sweep.py [hands] [--no-giveup] [--lever TYPE=donk,probe,giveup ...]
Same three 6-max tables and seeds as tests/test_persona_v2.py, so numbers match the test at 20000 hands.
"""
from __future__ import annotations

import argparse
import dataclasses
from collections import defaultdict

import numpy as np

from stalker.agents.persona import PRESETS_V2, PersonaAgent
from stalker.agents.persona_stats import measure_session

TYPES = list(PRESETS_V2)
TABLES = [TYPES[:6], TYPES[2:8], TYPES[:2] + TYPES[4:8]]


def sweep(hands: int, params: dict) -> dict[str, dict[str, float]]:
    acc: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for gi, grp in enumerate(TABLES):
        ss = np.random.SeedSequence(gi).spawn(6)
        agents = [PersonaAgent(params[n], np.random.default_rng(s)) for n, s in zip(grp, ss)]
        for n, st in zip(grp, measure_session(agents, hands, seed=50 + gi)):
            for k in ("wtsd", "fold_cbet_turn", "fold_river"):
                if getattr(st, k) is not None:
                    acc[n][k].append(getattr(st, k))
    return {n: {k: float(np.mean(v)) for k, v in d.items()} for n, d in acc.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("hands", type=int, nargs="?", default=20000)
    ap.add_argument("--no-giveup", action="store_true", help="giveup_weak=None for every type (turn/river folds as on main)")
    ap.add_argument("--lever", action="append", default=[], metavar="TYPE=donk,probe,giveup")
    a = ap.parse_args()
    params = dict(PRESETS_V2)
    if a.no_giveup:
        params = {n: dataclasses.replace(p, giveup_weak=None) for n, p in params.items()}
    for item in a.lever:
        n, v = item.split("=")
        d, p, g = (float(x) for x in v.split(","))
        params[n] = dataclasses.replace(params[n], donk_flop=d, probe_turn=p, giveup_weak=g)
    res = sweep(a.hands, params)
    print("type | donk,probe,giveup | wtsd | fold_turn(tgt) | fold_river(tgt)")
    for n in TYPES:
        p, r = params[n], res[n]
        print(f"{n} | {p.donk_flop},{p.probe_turn},{p.giveup_weak} | {r['wtsd']:.2f} | "
              f"{r['fold_cbet_turn']:.2f}({p.fold_cbet_turn}) | {r['fold_river']:.2f}({p.fold_river})")


if __name__ == "__main__":
    main()
