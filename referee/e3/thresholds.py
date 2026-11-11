"""Per-player-count LBR pass lines (ADR 0020) as a pure offline judge (#572).

Usage:
  python -m referee.e3.thresholds [--json] <summary.json>...
  python -m referee.e3.thresholds [--json] --job <name> --results-dir <ops cloud/results dir>
Exit 1 if any cell is `fail`; `insufficient` (too few seeds at the required hand count) is not a failure.
Record-only in CI (#576): `harness/cloud/launcher.py publish` writes `ops:cloud/verdicts/<job>.json`
via `record()` and never fails the job on it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# v1 (ADR 0020, bytes frozen) is kept as the history; v2 (ADR 0024) only raises players.3.min_seeds.lbr 1 -> 2.
THRESHOLDS_V1 = Path(__file__).with_name("lbr_thresholds_v1.json")
THRESHOLDS_V1_SHA256 = "e7f12f267264269666519684d51eebfdf7946f1a98795c0b7fac55a76344549a"
THRESHOLDS = Path(__file__).with_name("lbr_thresholds_v2.json")
THRESHOLDS_SHA256 = "1302d641f13f52338beed81765ecb11dcb12a0b0e166c51f0c03545c53d67275"
KINDS = ("lbr", "lbr_average")
VERDICT_SCHEMA = 1
RESULT_NAME = re.compile(r"([0-9]+)(?:\.summary)?\.json")
JOB_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


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


def collect(results_dir: Path, job: str) -> list[tuple[str, dict]]:
    """(run id, summary) of `job`'s results that have `by_players`, one per seed, oldest run first.

    A seed rerun (resume, re-evaluation) supersedes its earlier runs: the highest run id wins, since
    GitHub run ids only grow. Files that are not `<run id>[.summary].json` are ignored."""
    best: dict = {}
    for path in sorted(Path(results_dir).glob("*.json")):
        m = RESULT_NAME.fullmatch(path.name)
        if not m:
            continue
        try:
            s = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ThresholdError(f"{path.name}: unreadable result ({e}); fix or remove it on ops") from e
        if not isinstance(s, dict) or s.get("job") != job or not s.get("by_players"):
            continue
        run = m.group(1)
        prev = best.get(s.get("seed"))
        if prev is None or int(run) > int(prev[0]):
            best[s.get("seed")] = (run, s)
    return sorted(best.values(), key=lambda rs: int(rs[0]))


def to_json(result: dict) -> dict:
    """{n: {kind: {verdict, seeds, mean_lbr_bb, limit}}}: the stable machine form of judge()."""
    return {n: {kind: {"verdict": r["verdict"], "seeds": r["seeds"], "mean_lbr_bb": r["mean"], "limit": r["limit"]}
                for kind, r in kinds.items()} for n, kinds in result.items()}


def verdict(job: str, results_dir: Path) -> dict:
    """The record for `ops:cloud/verdicts/<job>.json`. Raises ThresholdError when nothing can be judged."""
    runs = collect(results_dir, job)
    if not runs:
        raise ThresholdError(f"no results of job {job!r} with by_players in {results_dir}")
    return {"schema_version": VERDICT_SCHEMA, "job": job, "thresholds": THRESHOLDS.name,
            "thresholds_sha256": THRESHOLDS_SHA256, "runs": [r for r, _ in runs],
            "seeds": [s.get("seed") for _, s in runs], "players": to_json(judge([s for _, s in runs]))}


def record(job: str, results_dir: Path, out_dir: Path, log=print) -> dict:
    """Write <out_dir>/<job>.json; never raises (record-only: a fail or a judge error must not fail the job)."""
    if not isinstance(job, str) or not JOB_NAME.fullmatch(job):
        log(f"lbr verdict not recorded: job name {job!r} is not a safe file name")
        return {"job": job, "error": "unsafe job name"}
    try:
        rec = verdict(job, results_dir)
        fails = sorted(f"{n}p {k}" for n, ks in rec["players"].items() for k, r in ks.items() if r["verdict"] == "fail")
        log(f"lbr verdict {job}: {'fail ' + ', '.join(fails) if fails else 'no fail'} ({len(rec['runs'])} runs)")
    except Exception as e:  # noqa: BLE001 — record-only: any judge error goes into the file, not the exit code
        rec = {"schema_version": VERDICT_SCHEMA, "job": job, "error": f"{type(e).__name__}: {e}"}
        log(f"lbr verdict {job}: error {rec['error']}")
    try:
        out = Path(out_dir) / f"{job}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    except OSError as e:
        log(f"lbr verdict {job}: not written ({e})")
    return rec


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m referee.e3.thresholds", description="ADR 0020 per-player-count LBR judge")
    p.add_argument("summaries", nargs="*", type=Path, help="<run>.summary.json files, one per seed")
    p.add_argument("--json", action="store_true", help="print the machine form instead of the table")
    p.add_argument("--job", help="with --results-dir: judge every result of this job (latest run per seed)")
    p.add_argument("--results-dir", type=Path, help="ops cloud/results directory")
    try:
        a = p.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if bool(a.job) != bool(a.results_dir) or bool(a.summaries) == bool(a.job):
        print("usage: python -m referee.e3.thresholds [--json] (<summary.json>... | --job NAME --results-dir DIR)",
              file=sys.stderr)
        return 2
    try:
        if a.job:
            rec = verdict(a.job, a.results_dir)
            result = {n: {k: {**r, "mean": r["mean_lbr_bb"]} for k, r in ks.items()} for n, ks in rec["players"].items()}
        else:
            result = judge([json.loads(Path(s).read_text(encoding="utf-8")) for s in a.summaries])
            rec = {"players": to_json(result)}
    except (ThresholdError, OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(rec, ensure_ascii=False, indent=1) if a.json else render(result))
    return 1 if any(r["verdict"] == "fail" for k in result.values() for r in k.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
