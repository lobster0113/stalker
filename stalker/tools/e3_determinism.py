"""E3 cross-runner determinism check (#447): `python -m stalker.tools.e3_determinism --iters 20000 --seed 2 --workers 4`.

The same E3 job, sha, seed and workers gave different tables on different CI runners while a local
rerun was bit-identical. The cause was CPU-dependent float results: numpy hands `a @ b` to BLAS, and
OpenBLAS picks its kernel per CPU (Haswell, SkylakeX, Zen, ...), each summing in its own order, so the
last bits of the preflop equity (169x169 matrix-vector products) and of a node's value differed by
runner. One flipped equity order or sampling threshold sends the run down another trajectory.

This tool trains the same small config once per numeric setting, each in a fresh process whose
environment emulates another runner (BLAS kernel and threads, numpy's SIMD dispatch, numba on/off),
and compares a fingerprint: hashes of the range-equity outputs and the final regret table
(`E3MCCFR.regret_hash`). Any difference exits 1. The fast version runs in the tests
(tests/test_e3_determinism.py); the full 2x10^4-iteration comparison is this CLI, which is slow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time


def _dispatched_simd() -> str:
    """numpy's dispatch targets this CPU runs: disabling them all leaves numpy on its baseline loops."""
    try:
        from numpy._core._multiarray_umath import __cpu_dispatch__, __cpu_features__
    except ImportError:  # numpy < 2
        from numpy.core._multiarray_umath import __cpu_dispatch__, __cpu_features__
    return " ".join(f for f in __cpu_dispatch__ if __cpu_features__.get(f))


def settings(numba_off: bool = True) -> dict[str, dict[str, str]]:
    """Environment overrides, each standing in for a runner with different numeric code paths.

    The OpenBLAS core types are ones every x86-64 CI runner can execute (SkylakeX needs AVX-512); on a
    numpy built with another BLAS the variable is ignored and that setting just repeats the default."""
    out = {"default": {},
           "blas-sandybridge": {"OPENBLAS_CORETYPE": "Sandybridge"},
           "blas-prescott": {"OPENBLAS_CORETYPE": "Prescott"},
           "blas-1-thread": {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
           "blas-4-threads": {"OPENBLAS_NUM_THREADS": "4", "OMP_NUM_THREADS": "4"}}
    simd = _dispatched_simd()
    if simd:
        out["numpy-baseline-simd"] = {"NPY_DISABLE_CPU_FEATURES": simd}
    if numba_off:
        out["numba-off"] = {"NUMBA_DISABLE_JIT": "1"}
    return out


def fingerprint(tier: str = "beginner", players: int = 6, iters: int = 20, seed: int = 2, workers: int = 1,
                batch: int = 10) -> dict:
    """Hashes of what an E3 run computes, in this process's numeric environment."""
    import numpy as np

    from stalker.e2.eq_view import N, equity_vs
    from stalker.e3 import parallel
    from stalker.e3.mccfr import E3MCCFR
    from stalker.e3.tp_key import TIER_DEPTH, TIER_K

    # Range equity directly, so a kernel difference shows even when the short run below does not diverge.
    rng = np.random.default_rng(447)
    h = hashlib.sha256()
    for board in ((), (0, 13, 26), (5, 18, 31, 44), (2, 7, 19, 33, 50)):
        for _ in range(24 if board else 200):
            w = rng.random(N) * (rng.random(N) < rng.uniform(0.05, 1.0))
            h.update(np.ascontiguousarray(equity_vs(board, w), dtype="<f8").tobytes())
    m = E3MCCFR(seed, TIER_K[tier], players, TIER_DEPTH[tier])
    parallel.iterate(m, iters, workers, batch)
    return {"equity_sha256": h.hexdigest(), "regret_sha256": m.regret_hash(), "keys": len(m.regret),
            "nodes": m.nodes}


def run_setting(env: dict[str, str], tier: str, players: int, iters: int, seed: int, workers: int,
                batch: int, timeout: float | None = None) -> dict:
    full = {**os.environ, **env}
    cmd = [sys.executable, "-m", "stalker.tools.e3_determinism", "--probe", "--tier", tier, "--players", str(players),
           "--iters", str(iters), "--seed", str(seed), "--workers", str(workers), "--batch", str(batch)]
    t0 = time.monotonic()
    p = subprocess.run(cmd, env=full, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"probe failed under {env}: {p.stderr.strip()[-2000:]}")
    return {**json.loads(p.stdout.strip().splitlines()[-1]), "seconds": round(time.monotonic() - t0, 1)}


def compare(results: dict[str, dict]) -> list[str]:
    """Settings whose fingerprint differs from the default's, as readable lines (empty: all equal)."""
    base = results["default"]
    bad = []
    for name, r in results.items():
        diff = [k for k in ("equity_sha256", "regret_sha256", "keys", "nodes") if r[k] != base[k]]
        if diff:
            bad.append(f"{name}: {', '.join(diff)} differ from default ({r} vs {base})")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="E3 determinism across emulated runners (#447)")
    ap.add_argument("--tier", default="mid")
    ap.add_argument("--players", type=int, default=6)
    ap.add_argument("--iters", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=2)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--batch", type=int, default=500, help="iterations per worker between syncs (CI: E3_SYNC_BATCH)")
    ap.add_argument("--no-numba-off", action="store_true", help="skip the slow numba-disabled setting")
    ap.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.probe:
        print(json.dumps(fingerprint(a.tier, a.players, a.iters, a.seed, a.workers, a.batch)))
        return 0
    results = {name: run_setting(env, a.tier, a.players, a.iters, a.seed, a.workers, a.batch)
               for name, env in settings(not a.no_numba_off).items()}
    bad = compare(results)
    print(json.dumps({"results": results, "equal": not bad}, indent=1))
    for line in bad:
        print(f"NONDETERMINISTIC {line}; find the CPU-dependent float operation (BLAS @, SIMD reduction, "
              "fastmath) on the E3 path and make it fixed-order", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
