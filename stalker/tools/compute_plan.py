"""Compute estimate behind ADR 0017 (#314): TP-GTO training for the first D3 environments.

Every throughput is a CI value (train.yml run ids in ADR 0017 §2); every other input is a stated
assumption. The ADR's tables are this module's output, and tests/test_compute_plan.py checks them.

    python -m stalker.tools.compute_plan
"""
from __future__ import annotations

import json
import sys

SEEDS = 4                      # train.yml default for every reported result
JOB_MINUTES = 340              # train.yml timeout-minutes; RunPod MAX_JOB_MINUTES is 330
PIECE_MINUTES = 300            # training per resumable piece (#301); the rest of the job is setup, LBR, upload
FREE_CONCURRENT_JOBS = 20      # GitHub Actions free plan, public repo

# E3 6-max keys (CI): beginner run 40664565294 saturated ~1,715 keys at 1e5 iterations; mid run
# 40698160972 had ~44k keys at 1e5 with 42% visited < 10 times. Pro keys are the 9-max note's
# estimate (10^5-10^6, docs/research/2026-10-path-to-9max.md §3); 3e5 is the assumed midpoint.
KEYS = {"beginner": 1_715, "mid": 44_000, "pro": 300_000}
# Chain days count training only: the dispatch gap between pieces is left out (assumption).
# Visits per key that saturated the beginner table, applied to every tier (assumption).
ITERS_PER_KEY = 100_000 / KEYS["beginner"]

# it/s per seed (CI): beginner run 40724494778 mean 6.83; mid run 40698160972 6-10 (low end).
# Pro: assumed 0.75 x mid (more TP items per decision).
RATE_6MAX = {"beginner": 6.83, "mid": 6.0, "pro": 4.5}
# 9-max SNG: 6-max is ~2/3 of the 9-max tree depth (path-to-9max §2), keys barely grow with seats
# (E3-1: 6-max 1,406 vs 9-max 1,235 beginner keys), so same iterations at 1/1.5 the rate (assumption).
NINE_MAX_SLOWDOWN = 1.5

# RunPod CPU (jobs/e2-throughput-cpu.yaml): cpu3c, 2 vCPU, hourly cap $0.12; MCCFR is single-threaded,
# so one pod runs two seed chains. Speed vs the CI runner is #264's open measurement; assumed 1.0.
RUNPOD_POD_USD_H = 0.12
RUNPOD_SEEDS_PER_POD = 2
RUNPOD_SPEED_VS_CI = 1.0
MONTHLY_CAP_USD = 100          # harness/budget.json


def rows() -> list[dict]:
    out = []
    for env, slow in (("6max-cash-100bb", 1.0), ("9max-sng", NINE_MAX_SLOWDOWN)):
        for tier in ("beginner", "mid", "pro"):
            iters = round(KEYS[tier] * ITERS_PER_KEY, -4)
            rate = RATE_6MAX[tier] / slow
            chain_h = iters / rate / 3600
            seed_h = chain_h * SEEDS
            out.append({"env": env, "tier": tier, "iters": int(iters), "it_s": round(rate, 2),
                        "pieces": -(-int(iters) // int(rate * PIECE_MINUTES * 60)), "chain_days": round(chain_h / 24, 1),
                        "seed_hours": round(seed_h, 1),
                        "runpod_usd": round(seed_h / RUNPOD_SPEED_VS_CI / RUNPOD_SEEDS_PER_POD * RUNPOD_POD_USD_H, 2)})
    return out


def summary() -> dict:
    r = rows()
    seed_h = sum(x["seed_hours"] for x in r)
    usd = sum(x["runpod_usd"] for x in r)
    return {"seed_hours": round(seed_h, 1), "runpod_usd": round(usd, 2),
            "longest_chain_days": max(x["chain_days"] for x in r),
            "free_ci_seed_hours_per_day": FREE_CONCURRENT_JOBS * 24,
            "free_ci_days_if_perfectly_parallel": round(seed_h / (FREE_CONCURRENT_JOBS * 24), 1),
            "runpod_seed_hours_per_month_at_cap": round(MONTHLY_CAP_USD / RUNPOD_POD_USD_H * RUNPOD_SEEDS_PER_POD, 1)}


def main(argv=None) -> int:
    for x in rows():
        print(json.dumps(x))
    print(json.dumps(summary()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
