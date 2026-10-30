"""Per-iteration cost of a key variant against the plain key (#454). Local reference numbers, not a gate.

    python -m stalker.e3.cost_probe --iters 10
"""
from __future__ import annotations

import argparse
import time

from stalker.e3.mccfr import E3MCCFR


def seconds_per_iter(variant: str, iters: int = 10, seed: int = 0, k: int = 11, n: int = 6, depth: str = "full") -> float:
    m = E3MCCFR(seed, k, n, depth, key_variant=variant)
    m.iterate(1)   # warm-up: compiled kernels, first-use caches
    t = time.perf_counter()
    m.iterate(iters)
    return (time.perf_counter() - t) / iters


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=10)
    a = ap.parse_args()
    base, b1 = seconds_per_iter("", a.iters), seconds_per_iter("b1", a.iters)
    print(f"mid, 6 players, 1 process, {a.iters} iterations: plain {base:.3f} s/iter, b1 {b1:.3f} s/iter, ratio {b1 / base:.1f}x")


if __name__ == "__main__":
    main()
