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
    from referee.gate_r import e3_suite
    from referee.gate_r.cash_suite import run_cash_suite
    from referee.gate_r.suite import run_suite

    tally = run_suite()
    cash, _ = run_cash_suite()
    e3 = e3_suite.run_e3_suite()
    return {"gate_r_pass_rate": round(tally.pass_rate, 6), "gate_r_checks": tally.total,
            "gate_r_cash_pass_rate": round(cash.pass_rate, 6), "gate_r_cash_checks": cash.total,
            "gate_r_e3_pass_rate": round(e3.pass_rate, 6), "gate_r_e3_checks": e3.total}


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


# Fixed E0/E1 training runs for the Gate Q4 record; changing them breaks the trend, so bump deliberately.
E0_KUHN_ITERS = 1000
E0_LEDUC_ITERS = 300
E1_STACKS = (5.0, 10.0, 15.0)
E1_ITERS = 1500


def e0() -> dict:
    """Exact exploitability of unconstrained CFR+ on Kuhn and Leduc (Gate Q4, E0)."""
    from referee.anchors.toy import exploitability, kuhn, leduc
    from stalker.toy.cfr import CFRPlus

    out = {"e0_kuhn_iters": E0_KUHN_ITERS, "e0_leduc_iters": E0_LEDUC_ITERS}
    for name, game, iters in (("kuhn", kuhn.game(), E0_KUHN_ITERS), ("leduc", leduc.game(), E0_LEDUC_ITERS)):
        solver = CFRPlus(game)
        solver.iterate(iters)
        out[f"e0_{name}_cfr_exploitability"] = round(float(exploitability(game, solver.average_strategy())), 7)
    return out


def e1() -> dict:
    """Exact exploitability of the E1 push/fold TP bottleneck policies (Gate Q4, E1), chip EV, no ante.

    Policies see `hand.eq_call` (SB) / equity vs the shoving range (BB) on rank (quantile) scales;
    the uniform beginner scale is kept as the TP v0.1 contrast.
    """
    from stalker.e1 import tp_pushfold as tp

    def mean(tier, scale):
        vals = [tp.train(s, 0.0, tier, E1_ITERS, "called", scale) for s in E1_STACKS]
        return vals, round(sum(r.exploitability for r in vals) / len(vals), 6)

    out = {"e1_stacks": list(E1_STACKS), "e1_iters": E1_ITERS}
    for tier in ("beginner", "mid", "pro"):
        vals, out[f"e1_tp_{tier}_exploitability"] = mean(tier, "quantile")
    out["e1_nash_fp_exploitability"] = round(sum(r.nash_exploitability for r in vals) / len(vals), 6)
    _, out["e1_tp_uniform_beginner_exploitability"] = mean("beginner", "uniform")
    return out


def snapshot() -> dict:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    snap = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sha": sha,
            "source": os.environ.get("METRICS_SOURCE", "local")}
    snap.update(test_counts())
    snap.update(code_size())
    snap.update(gate_r())
    snap.update(gate_l())
    snap.update(e0())
    snap.update(e1())
    return snap


if __name__ == "__main__":
    print(json.dumps(snapshot()))
