"""Fit the PRESETS_V2 WTSD levers by seeded coordinate search (#569), then report at the test's 20000 hands.

Usage: python scripts/persona_fit.py [--hands 5000] [--seed 0] [--workers 4] [--passes 6] [--check 20000]
Prints the fitted `_WTSD_LEVERS` dict to paste into stalker/agents/persona.py and a per-type table.
"""
from __future__ import annotations

import argparse
import ast
import sys

import numpy as np

from stalker.agents.persona import PRESETS_V2
from stalker.agents.persona_fit import TYPES, WTSD_TARGET, current_levers, errors, fit, loss, measure, summarize


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hands", type=int, default=5000, help="hands per table during the search")
    ap.add_argument("--seed", type=int, default=0, help="coordinate-order seed")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--passes", type=int, default=6)
    ap.add_argument("--step", type=float, default=0.1)
    ap.add_argument("--check", type=int, default=20000, help="hands for the final report (0 = skip)")
    ap.add_argument("--start", default="", help="python dict literal of starting levers (default: current _WTSD_LEVERS)")
    a = ap.parse_args()
    start = ast.literal_eval(a.start) if a.start else current_levers()
    lev, val = fit(start, a.hands, np.random.default_rng(a.seed), step=a.step, max_passes=a.passes,
                   workers=a.workers, log=lambda s: print(s, file=sys.stderr, flush=True))
    print(f"search loss {val:.4f} at {a.hands} hands")
    print("_WTSD_LEVERS = {" + ", ".join(f'"{n}": {tuple(lev[n])}' for n in TYPES) + "}")
    if a.check:
        seats = measure(lev, a.check)
        m, e = summarize(seats), errors(seats)
        print(f"{a.check} hands: loss {loss(seats):.4f} turn {e['turn']:.3f} river {e['river']:.3f} "
              f"worst seat wtsd miss {e['wtsd_worst']:.3f}")
        print("type | wtsd(tgt) | turn fold(tgt) | river fold(tgt)")
        for n in TYPES:
            p = PRESETS_V2[n]
            print(f"{n} | {m[n]['wtsd']:.2f}({WTSD_TARGET[n]}) | {m[n]['fold_cbet_turn']:.2f}({p.fold_cbet_turn}) | "
                  f"{m[n]['fold_river']:.2f}({p.fold_river})")


if __name__ == "__main__":
    main()
