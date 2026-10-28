"""Batch-synchronous parallel E3 MCCFR (#318): one chain on several cores.

Each batch, every worker copies the shared regrets, runs its share of iterations sequentially on the
copy with its own generator, and returns what it changed. The parent adds the workers' regret changes
to the snapshot (clipped at 0, as the sequential update does) and their average-strategy sums, in
worker order, so the result depends only on (state, workers, batch). Workers do not see each other's
updates inside a batch; that staleness is the price of the speedup, and its cost is measured (#318).

workers=1 is the sequential `E3MCCFR.iterate`, unchanged, so a 1-worker run matches earlier runs.
Worker generators are seeded from the model's own generator, so checkpoints (#301) still continue
bit for bit.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

import numpy as np

from stalker.e3.mccfr import E3MCCFR


def _work(args) -> tuple[dict, dict, dict, int]:
    k, n, depth, regret, iterations, seed, iters = args
    m = E3MCCFR(0, k, n, depth)
    m.rng = np.random.default_rng(seed)
    m.regret = {key: r.copy() for key, r in regret.items()}
    m.iterations = iterations
    m.iterate(iters)
    delta = {}
    for key, r in m.regret.items():
        base = regret.get(key)
        d = r if base is None else r - base
        if base is None or d.any():
            delta[key] = d
    avg = {key: v for key, v in m.avg.items() if v is not None}
    return delta, avg, dict(m.visits), m.nodes


def split(iters: int, workers: int) -> list[int]:
    q, r = divmod(iters, workers)
    return [q + (w < r) for w in range(workers)]


def iterate(m: E3MCCFR, iters: int, workers: int = 1, batch: int = 500, pool: ProcessPoolExecutor | None = None) -> None:
    """Run `iters` more iterations of `m` on `workers` processes, syncing every `batch` iterations per worker."""
    if workers < 1 or batch < 1:
        raise ValueError(f"workers and batch must be >= 1, got workers={workers} batch={batch}")
    if workers == 1:
        m.iterate(iters)
        return
    own = pool is None
    pool = pool or ProcessPoolExecutor(workers)
    try:
        left = iters
        while left > 0:
            chunk = min(left, workers * batch)
            shares = [s for s in split(chunk, workers) if s > 0]
            seeds = m.rng.integers(0, 2**63, size=len(shares))
            jobs = [(m.k, m.n, m.depth, m.regret, m.iterations, int(sd), s) for sd, s in zip(seeds, shares)]
            # All results first: the pool pickles `jobs` (which hold m.regret) in a feeder thread.
            for delta, avg, visits, nodes in list(pool.map(_work, jobs)):
                for key, d in delta.items():
                    base = m.regret.get(key)
                    m.regret[key] = np.maximum(d if base is None else base + d, 0)
                for key, v in avg.items():
                    a = m.avg[key]
                    m.avg[key] = v if a is None else a + v
                for key, c in visits.items():
                    m.visits[key] += c
                m.nodes += nodes
            m.iterations += chunk
            left -= chunk
    finally:
        if own:
            pool.shutdown()
