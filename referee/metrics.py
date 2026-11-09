"""Compute the metrics snapshot that CI appends to ops:metrics/history.jsonl.

Only CI runs this for the record. Product metrics register here through referee-change PRs as
their evaluators come online. The retired Gate A/B and sufficiency keys (ADR 0008) were dropped
in #101; their last values stay in history.jsonl.

`e3_web_lbr` (#683) copies the newest `stalker.web.policy-lbr` cloud result (ADR 0020 per-player LBR,
limit, pass; backoff on/off) from `ops:cloud/results/<run id>.json` so the service-policy strength axis
has a history; it is `null` when ops or such a result is missing. `fresh` (#690) is true only when every
measured player count's page policy (`web/app/policy/mid-<n>.json` `run_id`) is the measured `policy_run`.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_counts(junit: str | None = None) -> dict:
    """Counts from the gates (tests) job's JUnit report when CI hands one over (METRICS_JUNIT, #312):
    the suite already ran on this sha, and rerunning it serially took most of the 30-minute budget.
    Without a report it runs the suite with the same workers as `gates full`."""
    junit = junit or os.environ.get("METRICS_JUNIT")
    if junit:
        if not Path(junit).is_file():
            raise SystemExit(f"METRICS_JUNIT={junit} not found; check the junit artifact step of gates (tests)")
        root = ET.parse(junit).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        n = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
        return {"tests_passed": n["tests"] - n["failures"] - n["errors"] - n["skipped"],
                "tests_failed": n["failures"] + n["errors"]}
    from referee.gates import FULL_TEST_WORKERS

    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *FULL_TEST_WORKERS],
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


def gate_s_e1() -> dict:
    """Gate S v0 (#280/#287) on E1: the Nash anchor and the TP bottleneck policies on rank scales.

    Record-only for the TP policies (GATES.md Gate S): the trend is kept here, `gates full` only
    checks the anchor and the discrimination policies.
    """
    from referee import gate_s
    from stalker.e1.tp_pushfold import gate_s_policy

    spec, sha = gate_s.load()

    def row(r):
        return {"passed": r["passed"], "tv_p95_sb": r["tv_p95_by_seat"]["sb"], "tv_p95_bb": r["tv_p95_by_seat"]["bb"],
                "tp_change_p95": r["tp_change_p95"], "tp_change_p95_points": r["tp_change_p95_points"], "stab_regret_mean_pct": r["stab_regret_mean_pct"],
                "stab_regret_p99_pct": r["stab_regret_p99_pct"], "cliff_ratio": r["cliff_ratio"],
                "golden_ok": sum(g["ok"] for g in r["golden"]), "golden_total": len(r["golden"])}

    pols = {"nash_anchor": row(gate_s.evaluate(gate_s.nash_policy, spec))}
    for tier in ("beginner", "mid", "pro"):
        pols[f"e1_tp_{tier}_quantile"] = row(gate_s.evaluate(gate_s_policy(tier, "quantile", iters=E1_ITERS), spec))
    return {"gate_s_e1": {"spots_sha256": sha, "policies": pols}}


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


def gate_f_e1() -> dict:
    """Gate F v0 (#281) on the same E1 spots: the tier's follower bot (synthetic error, the tier's sigma)
    on rank scales, bb/hand vs the Nash anchor's opponent and its increase over the noiseless policy."""
    from referee import gate_f
    from stalker.e1.tp_pushfold import gate_f_policy

    out = {}
    for tier in gate_f.SIGMA:
        m = gate_f.evaluate(gate_f_policy(tier, "quantile", iters=E1_ITERS), [(s, 0.0) for s in E1_STACKS], tier)["mean"]
        out[f"gate_f_e1_{tier}_nash_loss"] = m["nash_loss"]
        out[f"gate_f_e1_{tier}_nash_loss_added"] = m["nash_loss_added"]
    return out


WEB_LBR_SCHEMA = "stalker.web.policy-lbr"
WEB_POLICY_DIR = Path("web") / "app" / "policy"
_RESULT_PATH = re.compile(r"^cloud/results/(\d+)\.json$")


def _git(repo: Path, *args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=timeout)


def _page_run(repo: Path, players: str):
    """`run_id` of the page policy the service serves for this player count (file read only)."""
    try:
        doc = json.loads((repo / WEB_POLICY_DIR / f"mid-{players}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc.get("run_id") if isinstance(doc, dict) else None


def e3_web_lbr(repo: Path = ROOT, ref: str = "origin/ops", fetch: bool = True) -> dict:
    """Newest service-policy LBR result from ops, copied as is (no recomputation).

    The CI snapshot step runs before any ops worktree exists, so the files are read with `git show`.
    A failed fetch falls back to whatever `ref` already holds; no ref or no result gives `None`.
    `fresh` says whether the measured policy is still the one the pages serve: an old LBR must not
    read as the current service's trend once a page is re-exported (#690)."""
    try:
        if fetch:
            _git(repo, "fetch", "-q", "origin", "ops")
        ls = _git(repo, "ls-tree", "--name-only", f"{ref}:cloud/results")
        if ls.returncode != 0:
            return {"e3_web_lbr": None}
        runs = sorted((int(m.group(1)) for n in ls.stdout.split()
                       if (m := _RESULT_PATH.match(f"cloud/results/{n}"))), reverse=True)
        for run in runs:
            shown = _git(repo, "show", f"{ref}:cloud/results/{run}.json")
            try:
                doc = json.loads(shown.stdout) if shown.returncode == 0 else None
            except json.JSONDecodeError:
                continue
            if not isinstance(doc, dict) or doc.get("schema") != WEB_LBR_SCHEMA:
                continue
            by_players: dict = {}
            measured_run: dict = {}
            for mode, cells in sorted(doc.get("backoff", {}).items()):
                for n, cell in cells.items():
                    by_players.setdefault(str(n), {})[mode] = {
                        k: cell.get(k) for k in ("lbr_bb", "lbr_stderr_bb", "limit", "pass")}
                    if cell.get("policy_run") is not None:  # --from-pages results name the run each page file had (#695)
                        measured_run[str(n)] = cell["policy_run"]
            on = [m["on"]["pass"] for m in by_players.values() if "on" in m]
            policy_run = doc.get("policy_run")
            for n, m in by_players.items():
                m["page_run"] = _page_run(repo, n)
            def _want(n):  # per-player measured run when the result has it, else the one top-level run
                return measured_run.get(n, policy_run) if measured_run else policy_run
            fresh = bool(by_players) and all(
                _want(n) is not None and m["page_run"] is not None and str(m["page_run"]) == str(_want(n))
                for n, m in by_players.items())
            return {"e3_web_lbr": {"run": run, "policy_run": policy_run,
                                   "by_players": dict(sorted(by_players.items(), key=lambda kv: int(kv[0]))),
                                   "all_pass_on": bool(on) and all(p is True for p in on), "fresh": fresh}}
    except (OSError, subprocess.SubprocessError):
        pass
    return {"e3_web_lbr": None}


def snapshot() -> dict:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    snap = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sha": sha,
            "source": os.environ.get("METRICS_SOURCE", "local")}
    for part in (test_counts, code_size, gate_r, gate_l, gate_s_e1, e0, e1, gate_f_e1, e3_web_lbr):
        t0 = time.monotonic()
        snap.update(part())
        print(f"metrics: {part.__name__} {time.monotonic() - t0:.0f}s", file=sys.stderr, flush=True)
    return snap


if __name__ == "__main__":
    print(json.dumps(snapshot()))
