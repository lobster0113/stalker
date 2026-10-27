"""Compute the metrics snapshot that CI appends to ops:metrics/history.jsonl.

Only CI runs this for the record. Product metrics register here through referee-change PRs as
their evaluators come online. The retired Gate A/B and sufficiency keys (ADR 0008) were dropped
in #101; their last values stay in history.jsonl.
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

    from referee.gate_r.cash_suite import run_cash_suite

    tally = run_suite()
    cash, _ = run_cash_suite()
    return {"gate_r_pass_rate": round(tally.pass_rate, 6), "gate_r_checks": tally.total,
            "gate_r_cash_pass_rate": round(cash.pass_rate, 6), "gate_r_cash_checks": cash.total}


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


def snapshot() -> dict:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    snap = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sha": sha,
            "source": os.environ.get("METRICS_SOURCE", "local")}
    snap.update(test_counts())
    snap.update(code_size())
    snap.update(gate_r())
    snap.update(gate_l())
    return snap


if __name__ == "__main__":
    print(json.dumps(snapshot()))
