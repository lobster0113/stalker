"""E3 TP training on a many-core RunPod CPU pod (#333): `python -m stalker.tools.pod_train --out r.json`.

One chain, `--workers` processes (batch-synchronous, `stalker.e3.parallel`), trained until
`--minutes` of wall time, then evaluated exactly as the CI `e3-tp-*` jobs are
(`stalker.train_jobs.e3_evaluate`: LBR, coverage, field), so pod and CI numbers compare. The launcher
fetches one JSON of at most 256 MB (#346), so the result carries the summary plus the model as a compressed
`.npz` (base64): keys, regrets, average-strategy sums and visit counts, float32 if float64 does not
fit. `--unpack` turns it back into the CI layout (`<job>-seed<s>.ckpt.json`, `.policy.json`), so a
pod run can be evaluated, compared and resumed (`resume_run` in CI, or `--resume` here) like a CI one.
A float32 checkpoint continues the chain but not bit for bit.

Pod chains (#354): `cloud.yml resume_run=<id>` hands run <id>'s result to the next pod (launcher upload,
gzipped), which passes it as `--resume-result`; the job, tier, players and board.nut grid must match.
The checkpoint is kept under RESUME_BUDGET (the proxy's upload limit) when float32 fits, so a chain
can continue; above that the result still carries it, but only for `--unpack`.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import io
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from stalker.tools.pod_bench import machine, max_child_rss_mb, max_rss_mb

RESULT_BUDGET = 250 * 1024 * 1024  # under the launcher's 256 MB result cap (#346), with room for the summary
# = harness/cloud/launcher.py RESUME_MAX_BYTES (tested): the gzipped upload is about the npz size
RESUME_BUDGET = 95 * 1024 * 1024
GZIP_MAGIC = bytes((0x1F, 0x8B))
PROGRESS_SECONDS = 300


def job_name(tier: str, players: int) -> str:
    return f"e3-tp-{tier}{'' if players == 6 else players}-pod"


def load_resume_result(path: Path, tier: str, players: int) -> tuple[dict, str | None]:
    """`E3MCCFR.state()` from an earlier pod result (plain or gzipped JSON), plus the run it came from.

    Refuses a result of another job: its keys would mean other things in this table."""
    from stalker.e3 import tp_key as K

    raw = path.read_bytes()
    r = json.loads(gzip.decompress(raw) if raw[:2] == GZIP_MAGIC else raw)
    if not r.get("checkpoint"):
        raise SystemExit(f"{path}: no checkpoint to resume ({r.get('checkpoint_note', 'missing')}); "
                         "dispatch without resume_run")
    model = r.get("model") or {}
    want = {"job": job_name(tier, players), "tier": tier, "players": players}
    bad = [f"{k} {r.get(k)!r} != {v!r}" for k, v in want.items() if r.get(k) != v]
    bad += [f"model.{k} {model.get(k)!r} != {v!r}" for k, v in
            {"k": K.TIER_K[tier], "n": players, "depth": K.TIER_DEPTH[tier]}.items() if model.get(k) != v]
    if K.TIER_DEPTH[tier] == "pro" and model.get("nut_k", K.K_PRO) != K.NUT_K:
        bad.append(f"nut_k {model.get('nut_k', K.K_PRO)} != {K.NUT_K} (#332)")
    if bad:
        raise SystemExit(f"{path}: cannot resume this result here ({'; '.join(bad)}); pass a run of the same "
                         "job as resume_run, or start fresh without it")
    st = unpack_state(base64.b64decode(r["checkpoint"]["b64"]), model)
    return st, (str(r["run_id"]) if r.get("run_id") is not None else None)


def pack(m, dtype=np.float64) -> bytes:
    """The model's tables as a compressed npz (rng and counters travel in the JSON summary)."""
    keys = sorted(m.regret.keys() | {k for k, v in m.avg.items() if v is not None})
    zero = np.zeros(0)
    reg = [m.regret.get(k, zero) for k in keys]
    avg = [m.avg[k] if m.avg.get(k) is not None else zero for k in keys]
    buf = io.BytesIO()
    np.savez_compressed(buf, keys=np.array("\n".join(keys).encode()),
                        reg_len=np.array([len(r) for r in reg], dtype=np.int16),
                        avg_len=np.array([len(a) for a in avg], dtype=np.int16),
                        reg=np.concatenate(reg + [zero]).astype(dtype), avg=np.concatenate(avg + [zero]).astype(dtype),
                        visits=np.array([m.visits.get(k, 0) for k in keys], dtype=np.int64))
    return buf.getvalue()


def unpack_state(blob: bytes, meta: dict) -> dict:
    """`E3MCCFR.state()` data from `pack` output plus the summary's `model` block."""
    z = np.load(io.BytesIO(blob))
    raw = bytes(z["keys"])
    keys = raw.decode().split("\n") if raw else []
    regret, avg, visits = {}, {}, {}
    ri = ai = 0
    for k, rl, al, v in zip(keys, z["reg_len"], z["avg_len"], z["visits"]):
        if rl:
            regret[k] = z["reg"][ri:ri + rl].astype(float).tolist()
        if al:
            avg[k] = z["avg"][ai:ai + al].astype(float).tolist()
        if v:
            visits[k] = int(v)
        ri, ai = ri + int(rl), ai + int(al)
    return {"version": 1, **meta, "regret": regret, "avg": avg, "visits": visits}


def train(tier: str, players: int, workers: int, minutes: float, seed: int, batch: int,
          resume: dict | None = None, log=lambda s: print(s, file=sys.stderr, flush=True)):
    from stalker.e3 import parallel
    from stalker.e3.mccfr import E3MCCFR
    from stalker.e3.tp_key import TIER_DEPTH, TIER_K

    m = E3MCCFR.from_state(resume) if resume else E3MCCFR(seed, TIER_K[tier], players, TIER_DEPTH[tier])
    start_iters, timing = m.iterations, {}
    t0 = time.monotonic()
    deadline, next_log = t0 + minutes * 60, t0 + PROGRESS_SECONDS
    with ProcessPoolExecutor(workers) if workers > 1 else _NoPool() as p:
        while time.monotonic() < deadline:
            parallel.iterate(m, workers * batch, workers, batch, pool=p if workers > 1 else None, timing=timing)
            if time.monotonic() >= next_log:
                dt = time.monotonic() - t0
                log(json.dumps({"iters": m.iterations, "keys": len(m.regret), "minutes": round(dt / 60, 1),
                                "iters_per_s": round((m.iterations - start_iters) / dt, 1)}))
                next_log += PROGRESS_SECONDS
    train_s = time.monotonic() - t0
    done = m.iterations - start_iters
    total = max(timing.get("total", 0.0), 1e-9)
    return m, {"chunk_iters": done, "resumed_from": start_iters, "train_seconds": round(train_s, 1),
               "iters_per_s": round(done / max(train_s, 1e-6), 2),
               "sync_frac": round(max(0.0, total - timing.get("compute", 0.0)) / total, 3)}


class _NoPool:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def run(tier: str, players: int, workers: int, minutes: float, seed: int, batch: int, resume: dict | None = None,
        budget: int = RESULT_BUDGET, resume_budget: int = RESUME_BUDGET, resumed_from_run: str | None = None) -> dict:
    from stalker.train_jobs import e3_evaluate

    m, stats = train(tier, players, workers, minutes, seed, batch, resume)
    res = {"job": job_name(tier, players), "tier": tier, "players": players, "seed": seed, "workers": workers,
           "batch": batch, "iters": m.iterations, "resumed_from_run": resumed_from_run, **stats}
    res.update(e3_evaluate(m, seed))
    res["model"] = {"k": m.k, "n": m.n, "depth": m.depth, "iterations": m.iterations, "nodes": m.nodes,
                    "rng": m.rng.bit_generator.state, **m._grid()}
    res.update(_checkpoint(m, budget, resume_budget))
    res.update(max_rss_mb=max_rss_mb(), max_child_rss_mb=max_child_rss_mb(), machine=machine())
    return res


def _checkpoint(m, budget: int, resume_budget: int) -> dict:
    """float64 if the next pod can take it, else float32; past the resume limit, whatever fits the result."""
    blobs: dict = {}

    def blob(dtype):
        if dtype not in blobs:
            blobs[dtype] = pack(m, dtype)
        return blobs[dtype]

    fits = {"resume": lambda b: len(b) + 1024 * 1024 < resume_budget,
            "result": lambda b: len(b) * 4 // 3 + 64 * 1024 < budget}
    for limit in ("resume", "result"):
        for dtype in (np.float64, np.float32):
            b = blob(dtype)
            if fits["result"](b) and fits[limit](b):
                out = {"checkpoint": {"format": "npz", "dtype": np.dtype(dtype).name,
                                      "b64": base64.b64encode(b).decode()}}
                if limit == "result":
                    out["checkpoint_note"] = (f"npz {len(b)} bytes is over the {resume_budget}-byte pod upload "
                                              "limit: unpack it, but a pod chain cannot resume from it")
                return out
    return {"checkpoint": None, "checkpoint_note": f"model npz over {budget} bytes even as float32; summary only"}


def unpack(result: Path, out: Path) -> list[Path]:
    """Write a pod result's model in the CI artifact layout; returns the files written."""
    from stalker.e3.mccfr import E3MCCFR

    r = json.loads(result.read_text(encoding="utf-8"))
    if not r.get("checkpoint"):
        raise SystemExit(f"{result}: no checkpoint in this result ({r.get('checkpoint_note', 'missing')})")
    st = unpack_state(base64.b64decode(r["checkpoint"]["b64"]), r["model"])
    m = E3MCCFR.from_state(st)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{r['job']}-seed{r['seed']}"
    ck, pol = out / f"{stem}.ckpt.json", out / f"{stem}.policy.json"
    ck.write_text(json.dumps(st), encoding="utf-8")
    pol.write_text(json.dumps({"average": m.policy(), "current": m.current_policy()}), encoding="utf-8")
    return [ck, pol]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tier", default="pro", choices=("beginner", "mid", "pro"))
    ap.add_argument("--players", type=int, default=6)
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--minutes", type=float, default=60, help="training wall time; evaluation comes after")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--batch", type=int, default=500, help="iterations per worker between syncs")
    ap.add_argument("--resume", type=Path, help="a CI-layout .ckpt.json to continue")
    ap.add_argument("--resume-result", type=Path, help="an earlier pod result (JSON, may be gzipped) to continue")
    ap.add_argument("--sha-file", type=Path, help="file holding the source commit (the pod reads it from the tarball)")
    ap.add_argument("--unpack", type=Path, help="instead of training: write this pod result's model to --out (a folder)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.unpack:
        for f in unpack(a.unpack, a.out):
            print(f)
        return 0
    if a.workers < 1 or a.minutes <= 0 or a.batch < 1:
        raise SystemExit("--workers and --batch must be >= 1 and --minutes > 0")
    if a.resume and a.resume_result:
        raise SystemExit("pass --resume or --resume-result, not both")
    resume, from_run = (json.loads(a.resume.read_text(encoding="utf-8")) if a.resume else None), None
    if a.resume_result:
        resume, from_run = load_resume_result(a.resume_result, a.tier, a.players)
    res = run(a.tier, a.players, a.workers, a.minutes, a.seed, a.batch, resume, resumed_from_run=from_run)
    res["sha"] = a.sha_file.read_text(encoding="utf-8").strip() if a.sha_file and a.sha_file.exists() else ""
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
