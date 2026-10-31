"""E3 parallel MCCFR scaling probe for one machine (#321): `python -m stalker.tools.parallel_bench --out r.json`.

Warms one E3 model (so the regret table has the size a real run syncs), then, from that same state,
runs the batch-synchronous trainer (`stalker.e3.parallel`, #318) at each worker count for the same
iterations per worker and records iterations/s, efficiency against one worker and `sync_frac`: the
share of wall time not spent in the slowest worker's own iterations (snapshot pickling and transfer,
merging, stragglers; 0 for one worker), so a low efficiency can be split into sync cost and slower
cores. Workers are started before the clock, as a long training run starts them once.
`max_child_rss_mb` is the largest single worker's peak RSS, not a sum: peak pod memory is roughly
workers x that plus the parent's `max_rss_mb`. Meant for a RunPod CPU pod
(`jobs/e3-parallel-scaling.yaml`); a local run gives reference numbers only (CLAUDE.md).
"""
from __future__ import annotations

import argparse
import copy
import json
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from stalker.tools.pod_bench import machine, max_child_rss_mb, max_rss_mb

WORKERS = (1, 4, 8, 16, 32)


def bench(workers=WORKERS, tier: str = "mid", players: int = 6, warm: int = 4000, per_worker: int = 300,
          batch: int = 300, seed: int = 1) -> dict:
    from stalker.e3 import parallel
    from stalker.e3.mccfr import E3MCCFR
    from stalker.e3.tp_key import TIER_DEPTH, TIER_K

    workers = sorted(set(workers))
    if not workers or workers[0] < 1:
        raise SystemExit("workers must be positive counts, e.g. --workers 1,4,8,16,32")
    base = E3MCCFR(seed, TIER_K[tier], players, TIER_DEPTH[tier])
    t0 = time.monotonic()
    with ProcessPoolExecutor(workers[-1]) as p:
        parallel.iterate(base, warm, workers[-1], max(1, warm // workers[-1]), pool=p)
    warm_s = time.monotonic() - t0
    t0 = time.monotonic()
    snap = pickle.dumps(base.regret)
    pickle_s = time.monotonic() - t0
    rows = []
    for w in workers:
        m, iters = copy.deepcopy(base), per_worker * w
        with ProcessPoolExecutor(w) as p:
            if w > 1:  # start the workers and import the trainer in them before the clock
                parallel.iterate(copy.deepcopy(base), w, w, 1, pool=p)
            t0, timing = time.monotonic(), {}
            parallel.iterate(m, iters, w, batch, pool=p if w > 1 else None, timing=timing)
            dt = time.monotonic() - t0
        sync = max(0.0, timing["total"] - timing["compute"]) / max(timing["total"], 1e-9)
        rows.append({"workers": w, "iters": iters, "seconds": round(dt, 1), "iters_per_s": round(iters / max(dt, 1e-6), 2),
                     "sync_frac": round(sync, 3), "merge_s": round(timing["merge"], 2)})
        print(json.dumps(rows[-1]), file=sys.stderr, flush=True)
    one = rows[0]["iters_per_s"] / rows[0]["workers"]
    for r in rows:
        r["efficiency"] = round(r["iters_per_s"] / (r["workers"] * one), 3)
    return {"job": "e3-parallel-scaling", "tier": tier, "players": players, "seed": seed, "warm_iters": warm,
            "warm_seconds": round(warm_s, 1), "keys": len(base.regret), "snapshot_mb": round(len(snap) / 1e6, 2),
            "snapshot_pickle_s": round(pickle_s, 3), "per_worker": per_worker, "batch": batch, "rows": rows,
            "max_rss_mb": max_rss_mb(), "max_child_rss_mb": max_child_rss_mb(), "machine": machine()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workers", default=",".join(map(str, WORKERS)), help="comma-separated worker counts")
    ap.add_argument("--tier", default="mid")
    ap.add_argument("--players", type=int, default=6)
    ap.add_argument("--warm", type=int, default=4000)
    ap.add_argument("--per-worker", type=int, default=300)
    ap.add_argument("--batch", type=int, default=300)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--sha-file", type=Path, help="file holding the source commit (the pod reads it from the tarball)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        ws = [int(x) for x in a.workers.split(",") if x.strip()]
    except ValueError:
        raise SystemExit(f"--workers must be integers like 1,4,8, got {a.workers!r}")
    res = bench(ws, a.tier, a.players, a.warm, a.per_worker, a.batch, a.seed)
    res["sha"] = a.sha_file.read_text(encoding="utf-8").strip() if a.sha_file and a.sha_file.exists() else ""
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
