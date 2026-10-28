"""E2-3: TP tier bottleneck table (#187). Trains MCCFR at each tier's card resolution and measures
the LBR lower bound on common random deals, so tiers differ only in what the policy may see.

    python -m stalker.e2.tiers --iters 2000 5000 --hands 400 --seed 1

Coarse tiers have fewer infosets and converge in fewer iterations, so the table reports several
iteration counts: a gap that persists as iterations grow is the bottleneck, not slow convergence.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from referee.e2.lbr import exploitability_lb
from stalker.e2.abstraction import TIERS
from stalker.e2.mccfr import MCCFR


def table(iters: list[int], hands: int, seed: int, tiers=tuple(TIERS)) -> list[dict]:
    rows = []
    for tier in tiers:
        m = MCCFR(seed, TIERS[tier])
        done, t0 = 0, time.monotonic()
        for n in sorted(iters):
            m.iterate(n - done)
            done = n
            lb = exploitability_lb(m.policy(), hands, seed=seed * 1000 + 7, abstraction=TIERS[tier])
            rows.append({"tier": tier, "abstraction": TIERS[tier].name, "iters": n, "infosets": len(m.regret),
                         "train_s": round(time.monotonic() - t0, 1), **lb})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--iters", type=int, nargs="+", default=[2000])
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tiers", nargs="+", choices=sorted(TIERS), default=list(TIERS))
    a = ap.parse_args(argv)
    for row in table(a.iters, a.hands, a.seed, a.tiers):
        print(json.dumps(row), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
