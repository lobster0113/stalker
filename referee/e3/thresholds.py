"""Per-player-count LBR pass lines (ADR 0020) as a pure offline judge (#572).

Not wired into CI yet. Usage: python -m referee.e3.thresholds <summary.json>...
Exit 1 if any cell is `fail`; `insufficient` (too few seeds at the required hand count) is not a failure.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

THRESHOLDS = Path(__file__).with_name("lbr_thresholds_v1.json")
THRESHOLDS_SHA256 = "e7f12f267264269666519684d51eebfdf7946f1a98795c0b7fac55a76344549a"
KINDS = ("lbr", "lbr_average")


class ThresholdError(ValueError):
    pass


def load_thresholds(path: Path = THRESHOLDS, pinned: str | None = THRESHOLDS_SHA256) -> dict:
    raw = path.read_bytes()
    if pinned is not None and hashlib.sha256(raw).hexdigest() != pinned:
        raise ThresholdError(f"{path.name}: sha256 differs from the pinned one; the lines are fixed by ADR 0020. "
                             "Add a new versioned file and update the pin instead of editing it.")
    return json.loads(raw)


def judge(summaries: list[dict], table: dict | None = None) -> dict:
    """{n: {kind: {"verdict": pass|fail|insufficient, "mean", "limit", "seeds"}}} for n in the table."""
    table = table or load_thresholds()
    if not summaries:
        raise ThresholdError("no summaries given; pass at least one <run>.summary.json")
    seeds = [s.get("seed") for s in summaries]
    if len(set(seeds)) != len(seeds):
        raise ThresholdError(f"duplicate seed in {sorted(seeds, key=str)}; pass one summary per seed")
    for key in ("job", "policy"):
        vals = {s.get(key) for s in summaries}
        if len(vals) > 1:
            raise ThresholdError(f"summaries mix several {key} values {sorted(map(str, vals))}; judge one {key} at a time")
    out: dict = {}
    for n, spec in table["players"].items():
        out[n] = {}
        for kind in KINDS:
            vals = []
            for s in summaries:
                cell = (s.get("by_players") or {}).get(n, {}).get(kind)
                if cell and cell.get("hands") == spec["hands"]:
                    vals.append(cell["lbr_bb"])
            limit = spec["lbr_max" if kind == "lbr" else "lbr_average_max"]
            if len(vals) < spec["min_seeds"][kind]:
                verdict, mean = "insufficient", (sum(vals) / len(vals) if vals else None)
            else:
                mean = sum(vals) / len(vals)
                verdict = "pass" if mean <= limit else "fail"
            out[n][kind] = {"verdict": verdict, "mean": mean, "limit": limit, "seeds": len(vals)}
    return out


def render(result: dict) -> str:
    lines = [f"{'players':>7} {'kind':<12} {'verdict':<13} {'mean':>7} {'limit':>6} seeds"]
    for n, kinds in result.items():
        for kind, r in kinds.items():
            mean = "-" if r["mean"] is None else f"{r['mean']:.3f}"
            lines.append(f"{n:>7} {kind:<12} {r['verdict']:<13} {mean:>7} {r['limit']:>6} {r['seeds']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    paths = (sys.argv[1:] if argv is None else argv)
    if not paths:
        print("usage: python -m referee.e3.thresholds <summary.json>...", file=sys.stderr)
        return 2
    try:
        result = judge([json.loads(Path(p).read_text(encoding="utf-8")) for p in paths])
    except (ThresholdError, OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(render(result))
    return 1 if any(r["verdict"] == "fail" for k in result.values() for r in k.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
