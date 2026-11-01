"""Batch-synchronous parallel E3 MCCFR (#318): one chain on several cores.

Each batch, every worker copies the shared regrets, runs its share of iterations sequentially on the
copy with its own generator, and returns what it changed. The parent adds the workers' regret changes
to the snapshot (clipped at 0, as the sequential update does) and their average-strategy sums, in
worker order, so the result depends only on (state, workers, batch). Workers do not see each other's
updates inside a batch; that staleness is the price of the speedup, and its cost is measured (#318).

workers=1 is the sequential `E3MCCFR.iterate`, unchanged, so a 1-worker run matches earlier runs.
Worker generators are seeded from the model's own generator, so checkpoints (#301) still continue
bit for bit.

Average-strategy ranges (#405): the parent retakes the snapshot at a sync once `range_every` iterations have
passed since the last one (so the effective interval is `range_every` rounded up to whole syncs) and every
worker of the batch reads that same snapshot; workers never refresh it, since each sees only its own sums.
"""
from __future__ import annotations

import pickle
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from stalker.e3.mccfr import E3MCCFR


def _work(args) -> tuple[dict, dict, dict, int, float]:
    k, n, depth, menu, raise_cap, blob, iterations, seed, iters, ranges, snap_blob, avg_rule, key_variant, stacks, mix = args
    regret = pickle.loads(blob)
    m = E3MCCFR(0, k, n, depth, menu, raise_cap, ranges, avg_rule=avg_rule, key_variant=key_variant,
                stacks=stacks, player_mix=mix)
    if snap_blob is not None:
        m.snap, m.snap_frozen = pickle.loads(snap_blob), True
    m.rng = np.random.default_rng(seed)
    m.regret = {key: r.copy() for key, r in regret.items()}
    m.iterations = iterations
    t0 = time.perf_counter()
    m.iterate(iters)
    compute = time.perf_counter() - t0
    delta = {}
    for key, r in m.regret.items():
        base = regret.get(key)
        d = r if base is None else r - base
        if base is None or d.any():
            delta[key] = d
    avg = {key: v for key, v in m.avg.items() if v is not None}
    return delta, avg, dict(m.visits), m.nodes, compute


def split(iters: int, workers: int) -> list[int]:
    q, r = divmod(iters, workers)
    return [q + (w < r) for w in range(workers)]


def iterate(m: E3MCCFR, iters: int, workers: int = 1, batch: int = 500, pool: ProcessPoolExecutor | None = None,
            timing: dict | None = None) -> None:
    """Run `iters` more iterations of `m` on `workers` processes, syncing every `batch` iterations per worker.

    `timing`, if given, accumulates seconds: `total` (wall), `compute` (per batch, the slowest worker's own
    iterations: the part more cores cannot shrink further) and `merge` (the parent folding results in).
    `total - compute` is the sync cost: snapshot pickling and transfer, merging and waiting on stragglers.
    """
    if workers < 1 or batch < 1:
        raise ValueError(f"workers and batch must be >= 1, got workers={workers} batch={batch}")
    if workers == 1:
        t0 = time.perf_counter()
        m.iterate(iters)
        if timing is not None:
            dt = time.perf_counter() - t0
            for k, v in (("total", dt), ("compute", dt), ("merge", 0.0)):
                timing[k] = timing.get(k, 0.0) + v
        return
    own = pool is None
    pool = pool or ProcessPoolExecutor(workers)
    snap_blob = None
    try:
        left = iters
        while left > 0:
            if m.refresh_snapshot() or (m.ranges == "average" and snap_blob is None):
                snap_blob = pickle.dumps(m.snap, protocol=pickle.HIGHEST_PROTOCOL)
            chunk = min(left, workers * batch)
            shares = [s for s in split(chunk, workers) if s > 0]
            seeds = m.rng.integers(0, 2**63, size=len(shares))
            t0 = time.perf_counter()
            # One pickle of the snapshot per batch, not one per worker: at 32 workers and a pro-sized
            # table the per-job pickling in the pool's single feeder thread was the serial part (#333).
            blob = pickle.dumps(m.regret, protocol=pickle.HIGHEST_PROTOCOL)
            jobs = [(m.k, m.n, m.depth, m.menu, m.raise_cap, blob, m.iterations, int(sd), s, m.ranges, snap_blob,
                     m.avg_rule, m.key_variant, m.stacks, m.player_mix)
                    for sd, s in zip(seeds, shares)]
            results = list(pool.map(_work, jobs))
            t1 = time.perf_counter()
            for delta, avg, visits, nodes, _ in results:
                for key, d in delta.items():
                    base = m.regret.get(key)
                    m.regret[key] = np.maximum(d if base is None else base + d, 0)
                for key, v in avg.items():
                    a = m.avg[key]
                    m.avg[key] = v if a is None else a + v
                for key, c in visits.items():
                    m.visits[key] += c
                m.nodes += nodes
            if timing is not None:
                t2 = time.perf_counter()
                for k, v in (("total", t2 - t0), ("compute", max(r[4] for r in results)), ("merge", t2 - t1)):
                    timing[k] = timing.get(k, 0.0) + v
            m.iterations += chunk
            left -= chunk
    finally:
        if own:
            pool.shutdown()
