"""python -m referee.gate_f [--scale S] [--stacks ...] [--out f.json]: Gate F v0 on E1, JSON to stdout.

For each tier, the E1 TP bottleneck policy of that tier followed with the tier's synthetic error
(GATES.md Gate F 1). Report-only: E1 has no persona field, so the exit code is 0 unless evaluation fails.
"""
import argparse
import json
import sys
from pathlib import Path

from referee import gate_f as F


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scale", default="quantile", choices=["quantile", "uniform"])
    ap.add_argument("--tiers", nargs="*", default=list(F.SIGMA), choices=list(F.SIGMA))
    ap.add_argument("--stacks", type=float, nargs="*")
    ap.add_argument("--antes", type=float, nargs="*")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    from stalker.e1.tp_pushfold import E1_ANTES, E1_STACKS, gate_f_policy

    spots = [(s, an) for an in (a.antes or E1_ANTES) for s in (a.stacks or E1_STACKS)]
    res = {"env": "e1", "error_model": "synthetic", "scale": a.scale, "verdict": F.VERDICT,
           "tiers": {t: F.evaluate(gate_f_policy(t, a.scale), spots, t) for t in a.tiers}}
    text = json.dumps(res, indent=1)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
