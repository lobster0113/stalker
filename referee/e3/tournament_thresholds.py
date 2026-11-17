"""Tournament non-inferiority judge (ADR 0030 decisions 1-3, #975), a pure offline judge.

Usage: python -m referee.e3.tournament_thresholds [--json] <tournament_ab result.json>...
Each input is one independently trained pair (A, B); `primary` is learner sim prize - ICM equity (B - A).
pass when ci_low > -delta over >= min_seeds pairs; fewer pairs is `insufficient` (not a failure).
Exit 1 only on `fail`. Not wired into CI yet (record-only; wiring is a follow-up issue).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

THRESHOLDS = Path(__file__).with_name("tournament_thresholds_v1.json")
THRESHOLDS_SHA256 = "ce5f83e6dec61a56642085acc2457b836989b425931a5c3cf7a6e6a5da697fca"
# Evaluation setup that must match across pairs; the policy files (a, b) legitimately differ per pair.
CONFIG_KEYS = ("presets", "remaining", "profiles", "level_indexes", "layouts", "games", "sym_games", "seed", "field")


class ThresholdError(ValueError):
    pass


def load_thresholds(path: Path = THRESHOLDS, pinned: str | None = THRESHOLDS_SHA256) -> dict:
    raw = path.read_bytes()
    if pinned is not None and hashlib.sha256(raw).hexdigest() != pinned:
        raise ThresholdError(f"{path.name}: sha256 differs from the pinned one; the line is fixed by ADR 0030. "
                             "Add a new versioned file and update the pin instead of editing it.")
    return json.loads(raw)


def _pair_id(r: dict, i: int) -> tuple:
    try:
        return (r["agents"]["A"]["sha256"], r["agents"]["B"]["sha256"])
    except (KeyError, TypeError):
        raise ThresholdError(f"result #{i} has no agents.A/B sha256; pass tournament_ab output as is") from None


def judge(results: list[dict], table: dict | None = None) -> dict:
    """{"verdict": pass|fail|insufficient, "mean", "se", "ci_low", "limit", "pairs"}."""
    table = table or load_thresholds()
    if not results:
        raise ThresholdError("no results given; pass at least one tournament_ab result.json")
    ids = [_pair_id(r, i) for i, r in enumerate(results)]
    if len(set(ids)) != len(ids):
        raise ThresholdError("the same trained pair (A and B sha256) appears twice; pass one result per independent pair")
    key = table["metric"]
    for i, r in enumerate(results):
        p = r.get(key)
        if not isinstance(p, dict) or "mean" not in p or "se" not in p:
            raise ThresholdError(f"result #{i} has no {key!r} with mean and se; rerun tournament_ab")
    cfg0 = {k: (results[0].get("args") or {}).get(k) for k in CONFIG_KEYS}
    for i, r in enumerate(results[1:], 1):
        cfg = {k: (r.get("args") or {}).get(k) for k in CONFIG_KEYS}
        if cfg != cfg0:
            diff = sorted(k for k in CONFIG_KEYS if cfg[k] != cfg0[k])
            raise ThresholdError(f"result #{i} differs in evaluation setup {diff}; evaluate all pairs with the same "
                                 "preset, remaining, games and seed")
    k = len(results)
    mean = math.fsum(r[key]["mean"] for r in results) / k
    se = math.sqrt(math.fsum(r[key]["se"] ** 2 for r in results)) / k
    ci_low = mean - table["z"] * se
    limit = -table["delta"]
    if k < table["min_seeds"]:
        verdict = "insufficient"
    else:
        verdict = "pass" if ci_low > limit else "fail"
    return {"verdict": verdict, "mean": mean, "se": se, "ci_low": ci_low, "limit": limit, "pairs": k}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("results", nargs="+", type=Path)
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)
    try:
        out = judge([json.loads(p.read_text(encoding="utf-8")) for p in ns.results])
    except (ThresholdError, OSError, ValueError) as e:
        print(f"tournament_thresholds: {e}", file=sys.stderr)
        return 2
    if ns.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    else:
        print(f"{out['verdict']}: mean {out['mean']:.5f} se {out['se']:.5f} ci_low {out['ci_low']:.5f} "
              f"limit {out['limit']:.5f} pairs {out['pairs']}")
    return 1 if out["verdict"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
