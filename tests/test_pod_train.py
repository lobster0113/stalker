"""#333: E3 training on a RunPod pod: result size, round trip to the CI layout, job spec."""
import json
import shlex
import sys
from pathlib import Path

import numpy as np
import pytest

from stalker.e3.mccfr import E3MCCFR
from stalker.tools import pod_train as P

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness" / "cloud"))
import launcher as L  # noqa: E402



def test_pack_round_trips_the_model_state():
    m = E3MCCFR(3, 5, 3, "basic")
    m.iterate(3)
    meta = {"k": m.k, "n": m.n, "depth": m.depth, "iterations": m.iterations, "nodes": m.nodes,
            "rng": m.rng.bit_generator.state}
    st = P.unpack_state(P.pack(m), meta)
    assert st == json.loads(json.dumps(m.state()))
    back, again = E3MCCFR.from_state(st), E3MCCFR.from_state(m.state())
    back.iterate(2), again.iterate(2)
    assert back.regret.keys() == again.regret.keys()
    assert all(np.array_equal(back.regret[k], again.regret[k]) for k in back.regret)


def test_run_writes_a_checked_result_and_unpacks_to_the_ci_layout(tmp_path):
    r = P.run("beginner", 3, 2, minutes=0.001, seed=1, batch=1)
    assert r["iters"] >= 2 and r["checkpoint"]["dtype"] == "float64"
    assert r["lbr"] is not None and r["field"] is None  # field is 6-max only
    body = json.dumps(r).encode()
    L.check_result(body)  # the launcher's own size and secret checks
    res = tmp_path / "r.json"
    res.write_bytes(body)
    ck, pol = P.unpack(res, tmp_path / "out")
    assert ck.name == "e3-tp-beginner3-pod-seed1.ckpt.json"
    assert E3MCCFR.from_state(json.loads(ck.read_text(encoding="utf-8"))).iterations == r["iters"]
    assert json.loads(pol.read_text(encoding="utf-8"))["current"]


def test_oversized_model_falls_back_to_float32_then_summary_only():
    r = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=1, budget=64 * 1024 + 1)
    assert r["checkpoint"] is None and "float32" in r["checkpoint_note"]


@pytest.mark.parametrize("spec", sorted((ROOT / "jobs").glob("e3-tp-*-pod32.yaml")), ids=lambda p: p.stem)
def test_job_spec_is_bounded_and_leaves_time_to_evaluate(spec):
    job = L.load_spec(spec)
    assert job.cpu_flavor and not job.gpu_type and job.vcpu == 32
    assert job.worst_case_usd <= 7.0, "one pod training run must stay cheap against the monthly cap"
    args = shlex.split(job.command.split("python3 -m stalker.tools.pod_train", 1)[1])
    assert args[args.index("--out") + 1] == job.result_path
    assert int(args[args.index("--workers") + 1]) <= job.vcpu
    # install + training + evaluation (LBR 2x1000 hands, field 1000 deals) inside the pod deadline
    assert float(args[args.index("--minutes") + 1]) + 60 <= job.max_minutes


def test_unpack_handles_tables_past_int16_offsets():
    # #355: offsets wrapped at 32767 in NumPy 2 (int + int16 stays int16); a real mid table has 54k keys
    m = E3MCCFR(1, 5, 3, "basic")
    for i in range(12_000):
        m.regret[f"k{i}"] = np.array([1.0, 2.0, float(i)])
        m.avg[f"k{i}"] = np.array([float(i), 1.0, 0.5])
        m.visits[f"k{i}"] = i + 1
    meta = {"k": m.k, "n": m.n, "depth": m.depth, "iterations": 0, "nodes": 0, "rng": m.rng.bit_generator.state}
    st = P.unpack_state(P.pack(m), meta)
    assert st["regret"]["k11999"] == [1.0, 2.0, 11999.0] and st["avg"]["k11999"] == [11999.0, 1.0, 0.5]
    assert st["visits"]["k11999"] == 12000
