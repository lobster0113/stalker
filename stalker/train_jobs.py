"""Allow-listed training jobs for the `train` workflow (GitHub Actions CPU runners, #184).

    python -m stalker.train_jobs run e2-mccfr --iters 20000 --seed 3 --out out/
    python -m stalker.train_jobs run e2-tier-beginner --iters 100000 --seed 1 --out out/   (#187)
    python -m stalker.train_jobs summarize e2-mccfr out/ > summary.json

Only names in JOBS can run, so a workflow input can never become an arbitrary command. Each run
writes `<out>/<job>-seed<S>.json` (settings, timings, result numbers, and a small policy digest);
`summarize` merges the per-seed files. Numbers produced here are CI numbers (CLAUDE.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from functools import partial
from pathlib import Path

SUMMARY_MAX_BYTES = 64 * 1024        # what may be pushed to ops per run
ARTIFACT_MAX_BYTES = 256 * 1024 ** 2  # one seed's output folder (uploaded as an artifact)
# Token shapes that must never reach ops or an artifact: GitHub, RunPod, AWS, PEM keys.
SECRET_PATTERNS = re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|rpa_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
                             r"|-----BEGIN [A-Z ]*PRIVATE KEY-----")


def _e2_mccfr(iters: int, seed: int, out: Path, tier: str = "baseline", name: str = "e2-mccfr") -> dict:
    from referee.e2.lbr import exploitability_lb
    from stalker.e2.abstraction import TIERS
    from stalker.e2.mccfr import MCCFR

    abstraction = TIERS[tier]
    t0 = time.monotonic()
    m = MCCFR(seed, abstraction)
    m.iterate(iters)
    train_s = time.monotonic() - t0
    policy = m.policy()
    (out / f"{name}-seed{seed}.policy.json").write_text(json.dumps(policy), encoding="utf-8")
    t1 = time.monotonic()
    # Same LBR deals for every tier and seed, so tiers differ only in what the policy sees (#187).
    lbr = exploitability_lb(policy, hands=400, seed=10_000 + seed, **({} if tier == "baseline" else {"abstraction": abstraction}))
    return {"iters": iters, "tier": tier, "abstraction": abstraction.to_json(), "train_seconds": round(train_s, 1), "iters_per_s": round(iters / max(train_s, 1e-6), 2),
            "infosets": len(m.regret), "lbr": lbr, "lbr_seconds": round(time.monotonic() - t1, 1),
            "policy_sha256": hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()}


def _e2_eq(iters: int, seed: int, out: Path, tier: str, name: str) -> dict:
    from referee.e2.lbr import exploitability_lb
    from stalker.e2.eq_view import EQ_TIERS, EqMCCFR

    t0 = time.monotonic()
    m = EqMCCFR(seed, EQ_TIERS[tier])
    m.iterate(iters)
    train_s = time.monotonic() - t0
    policy = m.policy()
    (out / f"{name}-seed{seed}.policy.json").write_text(json.dumps(policy), encoding="utf-8")
    t1 = time.monotonic()
    lbr = exploitability_lb(policy, hands=400, seed=10_000 + seed, view=m.view)
    return {"iters": iters, "tier": tier, "view": m.view.to_json(), "train_seconds": round(train_s, 1),
            "iters_per_s": round(iters / train_s, 2), "infosets": len(m.regret), "lbr": lbr,
            "lbr_seconds": round(time.monotonic() - t1, 1),
            "policy_sha256": hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()}


JOBS = {"e2-mccfr": _e2_mccfr,
        "e2-tier-beginner": partial(_e2_mccfr, tier="beginner", name="e2-tier-beginner"),
        "e2-tier-mid": partial(_e2_mccfr, tier="mid", name="e2-tier-mid"),
        "e2-eq-beginner": partial(_e2_eq, tier="beginner", name="e2-eq-beginner"),   # #188
        "e2-eq-mid": partial(_e2_eq, tier="mid", name="e2-eq-mid")}


def run(job: str, iters: int, seed: int, out: Path) -> Path:
    if job not in JOBS:
        raise SystemExit(f"unknown job {job!r}; allowed: {sorted(JOBS)}")
    if not 1 <= iters <= 10_000_000:
        raise SystemExit("iters must be between 1 and 10^7")
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    res = JOBS[job](iters, seed, out)
    path = out / f"{job}-seed{seed}.json"
    path.write_text(json.dumps({"job": job, "seed": seed, "wall_seconds": round(time.monotonic() - t0, 1),
                                **res}, indent=1), encoding="utf-8")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    if size > ARTIFACT_MAX_BYTES:
        raise SystemExit(f"{out}: {size} bytes > {ARTIFACT_MAX_BYTES}; write a smaller policy (prune or quantize) "
                         "or raise ARTIFACT_MAX_BYTES with a reason in the PR")
    check_clean(path.read_text(encoding="utf-8"), str(path))
    return path


def check_clean(text: str, where: str) -> None:
    """Refuse text that carries a token shape or the value of a secret-looking environment variable."""
    if SECRET_PATTERNS.search(text):
        raise SystemExit(f"{where}: looks like it contains a credential; results must hold numbers only")
    for k, v in os.environ.items():
        if re.search(r"TOKEN|SECRET|KEY|PASSWORD", k) and len(v) >= 8 and v in text:
            raise SystemExit(f"{where}: contains the value of ${k}; results must hold numbers only")


def summary_text(job: str, folder: Path) -> str:
    """The JSON pushed to ops: refuses unknown jobs, zero successful runs, oversize or secret-bearing output."""
    if job not in JOBS:
        raise SystemExit(f"unknown job {job!r}; allowed: {sorted(JOBS)}")
    s = summarize(job, folder)
    if not s["runs"]:
        raise SystemExit(f"no successful {job} runs under {folder}; nothing to push (see the run jobs' logs)")
    text = json.dumps(s, indent=1)
    if len(text.encode("utf-8")) > SUMMARY_MAX_BYTES:
        raise SystemExit(f"summary is {len(text.encode())} bytes > {SUMMARY_MAX_BYTES}; keep per-seed detail in the "
                         "artifacts and only aggregates in the summary")
    check_clean(text, "summary")
    return text


def summarize(job: str, folder: Path) -> dict:
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.rglob(f"{job}-seed*.json"))
            if not p.name.endswith(".policy.json")]
    out = {"job": job, "runs": len(runs), "seeds": [r["seed"] for r in runs]}
    if job.startswith("e2-") and runs:
        lb = [r["lbr"]["lbr_bb"] for r in runs]
        out.update({"iters": runs[0]["iters"], "iters_per_s_mean": round(sum(r["iters_per_s"] for r in runs) / len(runs), 2),
                    "lbr_bb_mean": round(sum(lb) / len(lb), 4), "lbr_bb_by_seed": lb})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("job")
    r.add_argument("--iters", type=int, required=True)
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("summarize")
    s.add_argument("job")
    s.add_argument("folder", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        print(run(a.job, a.iters, a.seed, a.out))
    else:
        print(summary_text(a.job, a.folder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
