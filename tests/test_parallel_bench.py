"""#321: E3 parallel MCCFR scaling probe and its job spec."""
import json
import shlex
import sys
from pathlib import Path

import pytest

from stalker.tools import parallel_bench as B

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness" / "cloud"))
import launcher as L  # noqa: E402

SPEC = ROOT / "jobs" / "e3-parallel-scaling.yaml"


def test_bench_rows_efficiency_and_machine():
    r = B.bench(workers=(2, 1), tier="beginner", players=3, warm=4, per_worker=2, batch=1)
    assert [row["workers"] for row in r["rows"]] == [1, 2]
    assert r["rows"][0]["efficiency"] == 1.0 and r["rows"][1]["iters"] == 4
    assert all(row["iters_per_s"] > 0 for row in r["rows"])
    assert r["keys"] > 0 and r["snapshot_mb"] >= 0 and r["machine"]["cpu_count"] >= 1
    json.dumps(r)  # the launcher fetches it as JSON


def test_bad_workers_fail_with_a_fix():
    with pytest.raises(SystemExit, match="--workers"):
        B.main(["--workers", "four", "--out", "x.json"])
    with pytest.raises(SystemExit, match="positive"):
        B.bench(workers=(0,))


def test_job_spec_is_bounded_and_writes_its_result_path():
    job = L.load_spec(SPEC)
    assert job.cpu_flavor and not job.gpu_type
    assert job.worst_case_usd <= 1.0, "one scaling probe must stay under $1 (#321, $100/month cap)"
    args = shlex.split(job.command.split("python3 -m stalker.tools.parallel_bench", 1)[1])
    assert args[args.index("--out") + 1] == job.result_path
    workers = [int(x) for x in args[args.index("--workers") + 1].split(",")]
    assert max(workers) <= job.vcpu, "more workers than the pod's vCPUs measures oversubscription"
    assert "[fast]" in job.command
    # Slowest per-core speed seen (CI, 6.45 it/s) at 50% efficiency must finish inside max_minutes.
    warm, per = int(args[args.index("--warm") + 1]), int(args[args.index("--per-worker") + 1])
    seconds = warm / (6.45 * max(workers) * 0.5) + sum(per / (6.45 * 0.5 if w > 1 else 6.45) for w in workers)
    assert seconds / 60 < job.max_minutes * 0.8
