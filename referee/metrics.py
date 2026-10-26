"""Compute the metrics snapshot that CI appends to ops:metrics/history.jsonl.

Only CI runs this for the record. Product metrics (strength, adaptation, typing fidelity)
register here through referee-change PRs as their evaluators come online.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_counts() -> dict:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True)
    text = r.stdout + r.stderr
    counts = {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|error|skipped)", text)}
    return {"tests_passed": counts.get("passed", 0),
            "tests_failed": counts.get("failed", 0) + counts.get("error", 0)}


def code_size() -> dict:
    n = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in (ROOT / "stalker").rglob("*.py"))
    return {"stalker_loc": n}


def gate_r() -> dict:
    from referee.gate_r.suite import run_suite

    tally = run_suite()
    return {"gate_r_pass_rate": round(tally.pass_rate, 6), "gate_r_checks": tally.total}


def gate_l(report=None) -> dict:
    """`report` lets tests inject a Report; CI leaves it None and runs the real Gate L."""
    if report is None:
        from referee.gate_l import run_gate_l

        report = run_gate_l()
    items = {k: [int(p), int(t)] for k, (p, t) in sorted(report.counts.items())}
    passed = sum(p for p, _ in items.values())
    total = sum(t for _, t in items.values())
    return {"gate_l_pass_rate": round(passed / total, 6) if total else 0.0, "gate_l_checks": total,
            "gate_l_items": items}


# Fixed dataset for the sufficiency metric; changing any of these breaks the trend, so bump deliberately.
SUFFICIENCY_PRESET = "sng6"
SUFFICIENCY_GAMES = 100
SUFFICIENCY_SEED = 1


def sufficiency(report: dict | None = None) -> dict:
    """Data-sufficiency metrics from a reference-bot dataset (fixed preset/games/seed above).

    `report` lets tests inject a typing report; CI leaves it None and generates the dataset.
    """
    if report is None:
        import tempfile

        from stalker.pipeline.generate import generate, resolve_config
        from stalker.typing.report import build_report

        cfg = resolve_config(SUFFICIENCY_PRESET)
        with tempfile.TemporaryDirectory() as tmp:
            decisions = generate(cfg, SUFFICIENCY_GAMES, SUFFICIENCY_SEED, tmp)
        report = build_report(decisions, players=cfg.players, seed=SUFFICIENCY_SEED)
    cells = report["cells"]
    n = len(cells)

    def rate(key: str) -> float:
        # An empty dataset must not read as sufficient.
        return round(sum(bool(c[key]) for c in cells) / n, 6) if n else 0.0

    return {"suff_cells": n, "suff_lessonable_cells": report["summary"]["lessonable_cells"],
            "suff_s1_rate": rate("s1"), "suff_s4_rate": rate("s4"), "suff_s5_rate": rate("s5"),
            "d1_preliminary": round(report["summary"]["d1_preliminary"]["lessonable_decision_share"], 6) if n else 0.0}


# Fixed Gate B pilot; editing the spec file changes gate_b_pilot_spec_sha256, which marks the trend break.
GATE_B_PILOT_SPEC = ROOT / "referee" / "gate_b" / "pilot_v1.json"
GATE_B_PILOT_CANDIDATE = "referee.gate_b.candidates:random_legal"


def gate_b_pilot(spec: dict | None = None) -> dict:
    """Gate B pilot keys (referee/GATES.md Gate B). `spec` lets tests shrink the run; CI uses the file."""
    from referee.gate_b.runner import load_spec, run_pilot

    file_spec, sha = load_spec(GATE_B_PILOT_SPEC)
    return run_pilot(spec if spec is not None else file_spec, sha, GATE_B_PILOT_CANDIDATE)


def snapshot() -> dict:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    snap = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sha": sha,
            "source": os.environ.get("METRICS_SOURCE", "local")}
    snap.update(test_counts())
    snap.update(code_size())
    snap.update(gate_r())
    snap.update(gate_l())
    snap.update(sufficiency())
    snap.update(gate_b_pilot())
    return snap


if __name__ == "__main__":
    print(json.dumps(snapshot()))
