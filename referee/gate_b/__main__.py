"""`python -m referee.gate_b --spec SPEC --candidate module:factory --out DIR`: exit 0 only on `pass`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from referee.gate_b.runner import PASS, load_spec, run_gate_b, to_json, to_markdown


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m referee.gate_b")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--candidate", required=True, help="module:factory; factory(config) returns rng -> Agent")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    spec, sha = load_spec(args.spec)
    result = run_gate_b(spec, sha, args.candidate)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "gate_b.json").write_text(to_json(result), encoding="utf-8")
    (out / "gate_b.md").write_text(to_markdown(result), encoding="utf-8")
    print(to_markdown(result))
    return 0 if result["verdict"] == PASS else 1


if __name__ == "__main__":
    sys.exit(main())
