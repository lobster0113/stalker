"""python -m referee.gate_s [--tier T] [--scale S] [--out f.json]: Gate S v0 on E1, JSON to stdout.

Evaluates the Nash anchor (must pass: the gate's own sanity check) and the E1 TP bottleneck policy
of the given tier. Exit code 1 if either fails.
"""
import argparse
import json
import sys
from pathlib import Path

from referee import gate_s as S


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tier", default="beginner", choices=["beginner", "mid", "pro"])
    ap.add_argument("--scale", default="quantile", choices=["quantile", "uniform"])
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    from stalker.e1.tp_pushfold import gate_s_policy

    spec, sha = S.load()
    res = {"spots": "v1", "sha256": sha,
           "policies": {"nash_anchor": S.evaluate(S.nash_policy, spec),
                        f"e1_tp_{a.tier}_{a.scale}": S.evaluate(gate_s_policy(a.tier, a.scale), spec)}}
    text = json.dumps(res, indent=1)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
    for name, r in res["policies"].items():
        for f in r["fails"]:
            print(f"Gate S [{name}] {f}", file=sys.stderr)
    return 0 if all(r["passed"] for r in res["policies"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
