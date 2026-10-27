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
import sys
import time
from functools import partial
from pathlib import Path


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
    return {"iters": iters, "tier": tier, "abstraction": abstraction.to_json(), "train_seconds": round(train_s, 1), "iters_per_s": round(iters / train_s, 2),
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


def _e3_tp(iters: int, seed: int, out: Path, tier: str, name: str, players: int = 6) -> dict:
    from referee.e3.lbr import exploitability_lb
    from stalker.e3.mccfr import E3MCCFR, coverage
    from stalker.e3.tp_key import TIER_K

    t0 = time.monotonic()
    m = E3MCCFR(seed, TIER_K[tier], players)
    m.iterate(iters)
    train_s = time.monotonic() - t0
    avg, cur = m.policy(), m.current_policy()
    (out / f"{name}-seed{seed}.policy.json").write_text(json.dumps({"average": avg, "current": cur}), encoding="utf-8")
    t1 = time.monotonic()
    # Same LBR deals for both policies; 100 hands per seat keeps the job inside the runner limit.
    lbr = {k: exploitability_lb(pol, 100, seed=10_000 + seed, k=m.k, n=players) for k, pol in (("average", avg), ("current", cur))}
    cov = coverage(m)
    return {"iters": iters, "tier": tier, "players": players, "train_seconds": round(train_s, 1),
            "iters_per_s": round(iters / train_s, 2), "infosets": len(m.regret), "coverage": cov,
            "lbr": lbr["current"], "lbr_average": lbr["average"], "lbr_seconds": round(time.monotonic() - t1, 1),
            "policy_sha256": hashlib.sha256(json.dumps(cur, sort_keys=True).encode()).hexdigest()}


JOBS = {"e2-mccfr": _e2_mccfr,
        "e2-tier-beginner": partial(_e2_mccfr, tier="beginner", name="e2-tier-beginner"),
        "e2-tier-mid": partial(_e2_mccfr, tier="mid", name="e2-tier-mid"),
        "e2-eq-beginner": partial(_e2_eq, tier="beginner", name="e2-eq-beginner"),   # #188
        "e2-eq-mid": partial(_e2_eq, tier="mid", name="e2-eq-mid"),
        "e3-tp-beginner": partial(_e3_tp, tier="beginner", name="e3-tp-beginner"),     # #196/#197, 6-max
        "e3-tp-mid": partial(_e3_tp, tier="mid", name="e3-tp-mid")}


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
    return path


def summarize(job: str, folder: Path) -> dict:
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.rglob(f"{job}-seed*.json"))
            if not p.name.endswith(".policy.json")]
    out = {"job": job, "runs": len(runs), "seeds": [r["seed"] for r in runs]}
    if job.startswith(("e2-", "e3-")) and runs:
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
        print(json.dumps(summarize(a.job, a.folder), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
