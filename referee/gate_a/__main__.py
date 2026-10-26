"""`python -m referee.gate_a --spots SET --candidate module:factory --out DIR`: exit 0 only on `pass`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from referee.gate_a.runner import PASS, SPEC_V1, load_spec, run_gate_a, to_json, to_markdown
from referee.gate_a.spots import SPOTS_V1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m referee.gate_a")
    ap.add_argument("--spots", default=str(SPOTS_V1))
    ap.add_argument("--spec", default=str(SPEC_V1))
    ap.add_argument("--candidate", required=True, help="module:factory; factory(config) returns a PolicyFn")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    spec, sha = load_spec(args.spec)
    result = run_gate_a(spec, sha, args.candidate, args.spots)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "gate_a.json").write_text(to_json(result), encoding="utf-8")
    (out / "gate_a.md").write_text(to_markdown(result), encoding="utf-8")
    print(to_markdown(result))
    return 0 if result["verdict"] == PASS else 1


if __name__ == "__main__":
    sys.exit(main())
