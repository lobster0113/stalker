"""#264: RunPod E2 throughput probe and its job spec."""
import json
import re
import shlex
import sys
from pathlib import Path

import pytest

from stalker.tools import pod_bench as PB

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness" / "cloud"))
import launcher as L  # noqa: E402

SPEC = ROOT / "jobs" / "e2-throughput-cpu.yaml"


def test_bench_reports_marks_decisions_and_machine():
    r = PB.bench(marks=(10, 30), seed=2, count_iters=5)
    assert [row["iters"] for row in r["marks"]] == [10, 30]
    assert all(row["iters_per_s"] > 0 and row["infosets"] > 0 for row in r["marks"])
    assert r["marks"][1]["infosets"] >= r["marks"][0]["infosets"]
    assert r["nodes_per_iter"] > 1 and r["decisions_per_s"] > 0
    assert r["machine"]["cpu_count"] >= 1 and isinstance(r["numba"], bool)
    json.dumps(r)  # the launcher fetches it as JSON


def test_counting_does_not_change_training():
    from stalker.e2.abstraction import TIERS
    from stalker.e2.mccfr import MCCFR

    a, b = MCCFR(4, TIERS["baseline"]), MCCFR(4, TIERS["baseline"])
    a.iterate(8)
    b.iterate(4)
    assert PB.count_nodes(b, 4) > 0
    assert "_walk" not in vars(b)  # the wrapper is removed afterwards
    assert a.policy() == b.policy()


def test_bad_marks_fail_with_a_fix():
    with pytest.raises(SystemExit, match="--marks"):
        PB.main(["--marks", "2e4", "--out", "x.json"])
    with pytest.raises(SystemExit, match="positive"):
        PB.bench(marks=(0,))


def test_main_writes_result_with_sha(tmp_path):
    (tmp_path / "SHA").write_text("a" * 40 + "\n", encoding="utf-8")
    out = tmp_path / "r" / "x.json"
    assert PB.main(["--marks", "5", "--count-iters", "2", "--sha-file", str(tmp_path / "SHA"), "--out", str(out)]) == 0
    r = json.loads(out.read_text(encoding="utf-8"))
    assert r["sha"] == "a" * 40 and r["marks"][0]["iters"] == 5


def test_job_spec_is_cheap_and_writes_its_result_path():
    job = L.load_spec(SPEC)
    assert job.cpu_flavor and not job.gpu_type
    assert job.worst_case_usd <= 0.25, "one probe must stay cheap (#264, NH-1 $100/month)"
    # the probe's --out must be the file the launcher fetches, and its flags must parse
    probe = job.command.split("python3 -m stalker.tools.pod_bench", 1)[1]
    args = shlex.split(probe)
    assert args[args.index("--out") + 1] == job.result_path
    assert "[fast]" in job.command, "install the numba extra so the #201 kernel is measured"
    marks = [int(x) for x in args[args.index("--marks") + 1].split(",")]
    # worst plausible speed (no numba, ~60 it/s locally) must still finish inside max_minutes
    assert max(marks) / 60 / 60 < job.max_minutes * 0.8
    assert re.search(r"tar\.gz/refs/heads/main", job.command)
