"""Build `stalker/data/preflop_equity.json`: 169 classes x equity vs 1..5 random hands.

    python -m stalker.tools.build_tables [--seed 20261023] [--nsim 50000] [--workers N]

Each (class, n_opp) cell gets its own seed derived from (seed, class index, n_opp), so the
output does not depend on worker count or scheduling order.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from stalker.core.cards import HAND_CLASSES, RANKS
from stalker.core.equity import equity_vs_ranges
from stalker.core.ranges import PREFLOP_TABLE, uniform_range

DEFAULT_SEED = 20261023
DEFAULT_NSIM = 50000
MAX_OPP = 5
DECIMALS = 4


def representative(cls: str) -> list[int]:
    """One concrete combo of a class; equity vs random hands is identical across its combos."""
    r1, r2 = RANKS.index(cls[0]), RANKS.index(cls[1])
    if r1 == r2:
        return [(r1 << 2) | 0, (r2 << 2) | 1]
    s2 = 0 if cls[2] == "s" else 1
    return [(r1 << 2) | 0, (r2 << 2) | s2]


def cell_equity(cls: str, n_opp: int, seed: int, nsim: int) -> float:
    rng = np.random.default_rng([seed, HAND_CLASSES.index(cls), n_opp])
    eq = equity_vs_ranges(representative(cls), [], [uniform_range()] * n_opp, nsim, rng)
    return round(eq, DECIMALS)


def _cell(args) -> float:
    return cell_equity(*args)


def build(classes=None, seed: int = DEFAULT_SEED, nsim: int = DEFAULT_NSIM,
          workers: int = 1, max_opp: int = MAX_OPP) -> dict[str, list[float]]:
    classes = list(HAND_CLASSES if classes is None else classes)
    jobs = [(c, n, seed, nsim) for c in classes for n in range(1, max_opp + 1)]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            vals = list(ex.map(_cell, jobs, chunksize=1))
    else:
        vals = [_cell(j) for j in jobs]
    return {c: vals[i * max_opp:(i + 1) * max_opp] for i, c in enumerate(classes)}


def dumps(table: dict[str, list[float]]) -> str:
    lines = [f"  {json.dumps(c)}: {json.dumps(v)}" for c, v in table.items()]
    return "{\n" + ",\n".join(lines) + "\n}\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m stalker.tools.build_tables")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--nsim", type=int, default=DEFAULT_NSIM)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--classes", nargs="*", help="subset of classes (default: all 169)")
    ap.add_argument("--out", type=Path, default=PREFLOP_TABLE)
    a = ap.parse_args(argv)
    bad = [c for c in a.classes or [] if c not in HAND_CLASSES]
    if bad:
        print(f"unknown classes {bad}; use names like AA, AKs, T9o", file=sys.stderr)
        return 2
    table = build(a.classes, a.seed, a.nsim, a.workers)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(dumps(table))
    return 0


if __name__ == "__main__":
    sys.exit(main())
