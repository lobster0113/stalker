"""`python -m referee.gate_r [--full] [--seeds N]`: per-item pass/total; exit 1 on any failure."""
from __future__ import annotations

import argparse
import sys

from referee.gate_r.suite import run_suite


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m referee.gate_r")
    ap.add_argument("--full", action="store_true", help="include slow presets (mtt180)")
    ap.add_argument("--seeds", type=int, default=5, help="seeds per preset variant and bot")
    args = ap.parse_args(argv)
    tally = run_suite(args.seeds, args.full)
    for item, (passed, total) in tally.counts.items():
        print(f"{item:18s} {passed}/{total}")
    print(f"gate_r: {tally.passed}/{tally.total} ({tally.pass_rate:.4%})")
    if tally.passed != tally.total:
        print("failures (first {}):".format(len(tally.failures)))
        print("\n".join("  " + f for f in tally.failures))
        print("fix the engine (stalker/tournament) or, if the rule itself is wrong, referee/gate_r via referee-change")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
