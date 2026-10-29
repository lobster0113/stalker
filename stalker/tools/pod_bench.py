"""E2 MCCFR throughput probe for one machine (#264): `python -m stalker.tools.pod_bench --out r.json`.

Runs the same training path as `train_jobs` (`MCCFR(seed, TIERS[tier]).iterate`) and records
iterations/s at each mark (default 20k and 200k, the sizes of the CI rows in
docs/research/2026-10-e2-throughput.md), decisions/s, peak memory and what the machine is (CPU model,
usable cores, cgroup quota, numba). Meant for a RunPod CPU pod (`jobs/e2-throughput-cpu.yaml`); a local
run gives reference numbers only (CLAUDE.md).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

MARKS = (20_000, 200_000)
# Counting wraps `_walk`, which slows it, so nodes per iteration come from a separate short stretch.
COUNT_ITERS = 1_000


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def machine() -> dict:
    cpu = next((ln.split(":", 1)[1].strip() for ln in _read("/proc/cpuinfo").splitlines()
                if ln.startswith("model name")), platform.processor())
    mem_kb = next((int(ln.split()[1]) for ln in _read("/proc/meminfo").splitlines() if ln.startswith("MemTotal:")), 0)
    # A pod's vCPU count is a cgroup quota, not the host's core count, so record both.
    quota = _read("/sys/fs/cgroup/cpu.max")
    affinity = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()
    return {"cpu_model": cpu, "cpu_count": os.cpu_count(), "affinity_cpus": affinity, "cgroup_cpu_max": quota,
            "mem_total_mb": round(mem_kb / 1024), "python": platform.python_version(), "platform": platform.platform()}


def max_rss_mb() -> float | None:
    try:
        import resource  # Unix only; the pod is Linux, a Windows dev box just gets None
    except ImportError:
        return None
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)  # Linux reports KiB


def max_child_rss_mb() -> float | None:
    """Peak RSS of the largest finished child process (not their sum), or None off Unix."""
    try:
        import resource
    except ImportError:
        return None
    return round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, 1)


def count_nodes(m, iters: int) -> int:
    """Decision-tree nodes visited (`_walk` calls) over `iters` more iterations."""
    calls = 0
    walk = m._walk

    def counted(*a, **kw):
        nonlocal calls
        calls += 1
        return walk(*a, **kw)

    m._walk = counted  # the recursion looks `self._walk` up on the instance, so it is counted too
    try:
        m.iterate(iters)
    finally:
        del m._walk
    return calls


def bench(marks=MARKS, seed: int = 1, tier: str = "baseline", count_iters: int = COUNT_ITERS) -> dict:
    from stalker.core import fast_eval
    from stalker.e2.abstraction import TIERS
    from stalker.e2.mccfr import MCCFR

    marks = sorted(set(marks))
    if not marks or marks[0] <= 0:
        raise SystemExit("marks must be positive iteration counts, e.g. --marks 20000,200000")
    m = MCCFR(seed, TIERS[tier])
    rows, done, t_start = [], 0, time.monotonic()
    for mark in marks:
        t0 = time.monotonic()
        m.iterate(mark - done)
        seg_s = time.monotonic() - t0
        total_s = time.monotonic() - t_start
        rows.append({"iters": mark, "seconds": round(total_s, 1), "iters_per_s": round(mark / max(total_s, 1e-6), 2),
                     "segment_iters_per_s": round((mark - done) / max(seg_s, 1e-6), 2), "infosets": len(m.regret)})
        done = mark
    nodes = count_nodes(m, count_iters) if count_iters > 0 else 0
    nodes_per_iter = nodes / count_iters if count_iters > 0 else None
    last = rows[-1]["segment_iters_per_s"]
    return {"job": "e2-throughput", "seed": seed, "tier": tier, "numba": bool(fast_eval.HAVE_NUMBA), "marks": rows,
            "count_iters": count_iters, "nodes_per_iter": None if nodes_per_iter is None else round(nodes_per_iter, 1),
            # decisions/s at the last segment's speed, the docs' "결정/초" (nodes visited per second)
            "decisions_per_s": None if nodes_per_iter is None else round(nodes_per_iter * last),
            "max_rss_mb": max_rss_mb(),
            "machine": machine()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--marks", default=",".join(map(str, MARKS)), help="comma-separated cumulative iteration counts")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tier", default="baseline")
    ap.add_argument("--count-iters", type=int, default=COUNT_ITERS)
    ap.add_argument("--sha-file", type=Path, help="file holding the source commit (the pod reads it from the tarball)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        marks = [int(x) for x in a.marks.split(",") if x.strip()]
    except ValueError:
        raise SystemExit(f"--marks must be integers like 20000,200000, got {a.marks!r}")
    res = bench(marks, a.seed, a.tier, a.count_iters)
    res["sha"] = a.sha_file.read_text(encoding="utf-8").strip() if a.sha_file and a.sha_file.exists() else ""
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("numba", "decisions_per_s", "max_rss_mb")} | {"marks": res["marks"]}),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
