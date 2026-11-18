"""Tournament non-inferiority judge (ADR 0030 decisions 1-3, #975), a pure offline judge.

Usage: python -m referee.e3.tournament_thresholds [--json] <tournament_ab result.json>...
Each input is one independently trained pair (A, B); `primary` is learner sim prize - ICM equity (B - A).
pass when ci_low > -delta over >= min_seeds pairs; fewer pairs is `insufficient` (not a failure).
`--recheck` (#983) checks ADR 0030's "되돌리는 조건" (between-pair sd > RECHECK_SD_FACTOR x within-pair se, or disjoint pair CIs).
Exit 1 only on `fail` (`--recheck` is record-only: exit 0). Not wired into CI yet (record-only; wiring is a follow-up issue).
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
# ADR 0030 "되돌리는 조건": between-pair sd above this multiple of the within-pair se means the noise model is wrong.
# A constant, not a table field, so the pinned table (and its sha256) stays untouched.
RECHECK_SD_FACTOR = 2.0
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


def recheck(results: list[dict], table: dict | None = None) -> dict:
    """ADR 0030 revert condition: {"status": ok|recheck|insufficient, "between_sd", "within_se", "ratio", "overlap", "pairs"}.
    Same input and ThresholdError rules as `judge`; `overlap` is True when every pair's 95% CIs overlap."""
    table = table or load_thresholds()
    judge(results, table)  # validates input (duplicates, setup mismatch, missing primary/se)
    key, z = table["metric"], table["z"]
    means = [float(r[key]["mean"]) for r in results]
    ses = [float(r[key]["se"]) for r in results]
    k = len(results)
    out = {"status": "insufficient", "between_sd": None, "within_se": None, "ratio": None, "overlap": None, "pairs": k}
    if k < 2:
        return out
    m = math.fsum(means) / k
    out["between_sd"] = math.sqrt(math.fsum((x - m) ** 2 for x in means) / (k - 1))
    out["within_se"] = math.sqrt(math.fsum(s * s for s in ses) / k)
    out["ratio"] = out["between_sd"] / out["within_se"] if out["within_se"] > 0 else None
    out["overlap"] = max(x - z * s for x, s in zip(means, ses)) <= min(x + z * s for x, s in zip(means, ses))
    if k >= table["min_seeds"]:
        wide = out["between_sd"] > RECHECK_SD_FACTOR * out["within_se"]
        out["status"] = "recheck" if wide or not out["overlap"] else "ok"
    return out


def recheck_from_ops(history: str | None = None, repo: Path | None = None, ref: str = "origin/ops") -> dict:
    """`recheck` over the runs of the last judged row of `metrics.tournament_trend` (history JSONL text, default
    `<ref>:metrics/history.jsonl`); run results are read with `git show <ref>:cloud/results/<run>.json`."""
    from referee import metrics

    repo = repo or metrics.ROOT
    try:
        if history is None:
            shown = metrics._git(repo, "show", f"{ref}:metrics/history.jsonl")
            if shown.returncode:
                return {"status": "insufficient", "error": f"no {ref}:metrics/history.jsonl"}
            history = shown.stdout
        rows = []
        for line in history.splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        last = [t for t in rows if isinstance(t, dict) and t.get("tournament_verdict") is not None]
        runs = (last[-1].get("tournament_runs") or []) if last else []
        if not runs:
            return {"status": "insufficient", "error": "no judged tournament row in history"}
        docs = []
        for run in runs:
            shown = metrics._git(repo, "show", f"{ref}:cloud/results/{run}.json")
            if shown.returncode:
                return {"status": "insufficient", "error": f"no {ref}:cloud/results/{run}.json"}
            docs.append(json.loads(shown.stdout))
        return recheck(docs)
    except (ThresholdError, OSError, ValueError) as e:
        return {"status": "insufficient", "error": f"{type(e).__name__}: {e}"[:300]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("results", nargs="*", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--recheck", action="store_true", help="check ADR 0030's revert condition from ops history")
    ap.add_argument("--history", type=Path, help="history JSONL (default: origin/ops:metrics/history.jsonl)")
    ns = ap.parse_args(argv)
    if ns.recheck:
        try:
            text = ns.history.read_text(encoding="utf-8") if ns.history else None
        except OSError as e:
            print(json.dumps({"status": "insufficient", "error": f"{e}"}, sort_keys=True))
            return 0
        print(json.dumps(recheck_from_ops(text), indent=2, sort_keys=True))
        return 0
    if not ns.results:
        ap.error("pass tournament_ab result.json files, or --recheck")
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
