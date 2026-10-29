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
    m = E3MCCFR(3, 5, 3, "basic", "tp6", None)  # non-default rules must survive the trip (#339)
    m.iterate(3)
    meta = {"k": m.k, "n": m.n, "depth": m.depth, "iterations": m.iterations, "nodes": m.nodes,
            "menu": m.menu, "raise_cap": m.raise_cap, "rng": m.rng.bit_generator.state}
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
    assert (r["model"]["menu"], r["model"]["raise_cap"]) == ("v1", 3)
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


def test_cpu5c_variant_matches_cpu3c_job_and_fits_the_measurement_budget():
    # #373: only the flavor and the price cap differ, so it/s per $ compares hosts, not jobs
    c3, c5 = (L.load_spec(ROOT / "jobs" / f) for f in ("e3-tp-mid9-pod32.yaml", "e3-tp-mid9-c5-pod32.yaml"))
    assert (c3.cpu_flavor, c5.cpu_flavor) == ("cpu3c", "cpu5c")
    assert c5.command == c3.command.replace(c3.result_path, c5.result_path)
    assert (c5.vcpu, c5.max_minutes) == (c3.vcpu, c3.max_minutes)
    assert 2 * c5.worst_case_usd <= 8.0, "two cpu5c runs are reserved against the issue budget of $8"


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


def test_unpack_reads_each_array_once(monkeypatch):
    # #355: NpzFile decompresses on every z[name]; reading per key made a 195k-key pro table take hours
    m = E3MCCFR(1, 5, 3, "basic")
    for i in range(50):
        m.regret[f"k{i}"], m.avg[f"k{i}"], m.visits[f"k{i}"] = np.array([1.0, 2.0]), np.array([0.5, 0.5]), 1
    blob, reads, load = P.pack(m), [], np.load

    class Counting:
        def __init__(self, z):
            self.z = z

        def __getitem__(self, name):
            reads.append(name)
            return self.z[name]

    monkeypatch.setattr(P.np, "load", lambda f: Counting(load(f)))
    meta = {"k": m.k, "n": m.n, "depth": m.depth, "iterations": 0, "nodes": 0, "rng": m.rng.bit_generator.state}
    P.unpack_state(blob, meta)
    assert sorted(reads) == sorted(set(reads)), reads


@pytest.fixture
def no_eval(monkeypatch):
    """The resume tests check the chain, not the evaluation (covered above), which is most of their time."""
    import stalker.train_jobs as TJ
    monkeypatch.setattr(TJ, "e3_evaluate", lambda m, seed: {"lbr": None})


def _pod_result_file(tmp_path, r, gz=False, run_id=None):
    import gzip
    body = json.dumps(r | ({"run_id": run_id} if run_id else {})).encode()
    f = tmp_path / ("r.json.gz" if gz else "r.json")
    f.write_bytes(gzip.compress(body) if gz else body)
    return f


def test_resume_result_continues_the_chain_and_records_the_run(tmp_path, no_eval):
    # #354: train -> result -> launcher payload (trimmed, gzipped) -> next pod -> iterations add up
    first = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=2)
    src = _pod_result_file(tmp_path, first)
    f = tmp_path / "upload.bin"
    f.write_bytes(L.resume_payload(src, "4242"))
    st, run_id = P.load_resume_result(f, "beginner", 3)
    assert run_id == "4242" and st["iterations"] == first["iters"]
    second = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=2, resume=st, resumed_from_run=run_id)
    assert second["resumed_from_run"] == "4242" and second["resumed_from"] == first["iters"]
    assert second["iters"] == first["iters"] + second["chunk_iters"] > first["iters"]
    assert first["resumed_from_run"] is None


def test_resume_result_cli_writes_the_continued_result(tmp_path, no_eval):
    first = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=2)
    f = _pod_result_file(tmp_path, first, gz=True, run_id="77")
    out = tmp_path / "out" / "r2.json"
    assert P.main(["--tier", "beginner", "--players", "3", "--workers", "1", "--minutes", "0.001", "--batch", "2",
                   "--resume-result", str(f), "--out", str(out)]) == 0
    r2 = json.loads(out.read_text(encoding="utf-8"))
    assert r2["resumed_from_run"] == "77" and r2["iters"] > first["iters"] == r2["resumed_from"]
    with pytest.raises(SystemExit, match="not both"):
        P.main(["--tier", "beginner", "--resume", str(f), "--resume-result", str(f), "--out", str(out)])


@pytest.mark.parametrize("change,msg", [
    ({"tier": "mid"}, "tier"), ({"players": 6}, "players"), ({"job": "e3-tp-beginner3-x"}, "job"),
    ({"checkpoint": None}, "no checkpoint")], ids=["tier", "players", "job", "no-ckpt"])
def test_resume_result_refuses_another_job(tmp_path, change, msg):
    r = {"job": "e3-tp-beginner3-pod", "tier": "beginner", "players": 3,
         "model": {"k": 5, "n": 3, "depth": "basic"}, "checkpoint": {"b64": ""}} | change
    with pytest.raises(SystemExit, match=msg):
        P.load_resume_result(_pod_result_file(tmp_path, r), "beginner", 3)


def test_resume_result_refuses_an_old_board_nut_grid(tmp_path):
    from stalker.e3 import tp_key as K
    r = {"job": "e3-tp-pro-pod", "tier": "pro", "players": 6, "checkpoint": {"b64": ""},
         "model": {"k": K.TIER_K["pro"], "n": 6, "depth": "pro", "nut_k": K.NUT_K + 1}}
    with pytest.raises(SystemExit, match="nut_k"):
        P.load_resume_result(_pod_result_file(tmp_path, r), "pro", 6)


def test_checkpoint_stays_under_the_pod_upload_limit_when_float32_fits():
    assert P.RESUME_BUDGET == L.RESUME_MAX_BYTES
    m = E3MCCFR(3, 5, 3, "basic")
    m.iterate(20)
    f64, f32 = len(P.pack(m)), len(P.pack(m, np.float32))
    big = 10 ** 9
    assert P._checkpoint(m, big, big)["checkpoint"]["dtype"] == "float64"
    c = P._checkpoint(m, big, (f64 + f32) // 2 + 1024 * 1024)
    assert c["checkpoint"]["dtype"] == "float32" and "checkpoint_note" not in c
    c = P._checkpoint(m, big, 1024 * 1024)  # neither fits the upload: still in the result, marked
    assert c["checkpoint"]["dtype"] == "float64" and "cannot resume" in c["checkpoint_note"]


def test_pod_jobs_take_the_resume_file():
    for spec in sorted((ROOT / "jobs").glob("e3-tp-*-pod32.yaml")):
        assert '${STALKER_RESUME:+--resume-result "$STALKER_RESUME"}' in L.load_spec(spec).command, spec.name

_BEGINNER3 = {"job": "e3-tp-beginner3-pod", "tier": "beginner", "players": 3, "checkpoint": {"b64": ""},
              "model": {"k": 5, "n": 3, "depth": "basic", "menu": "v1", "raise_cap": 3}}


@pytest.mark.parametrize("model,job,msg", [
    ({"menu": "tp6"}, {}, "menu"),                        # result tp6, job v1
    ({"raise_cap": None}, {}, "raise_cap"),               # result uncapped, job cap 3
    ({}, {"menu": "tp6"}, "menu"),                        # job tp6, result v1
    ({}, {"raise_cap": None}, "raise_cap"),               # job uncapped, result cap 3
    ({"raise_cap": 4}, {}, "raise_cap"),
], ids=["result-tp6", "result-nocap", "job-tp6", "job-nocap", "cap-4"])
def test_resume_result_refuses_other_game_rules(tmp_path, model, job, msg):
    # #339: the menu and raise cap change which actions a key has, so a table of other rules is refused
    r = _BEGINNER3 | {"model": _BEGINNER3["model"] | model}
    with pytest.raises(SystemExit, match=msg):
        P.load_resume_result(_pod_result_file(tmp_path, r), "beginner", 3, **job)


def test_resume_result_reads_a_result_from_before_the_rules_as_v1_cap3(tmp_path):
    r = _BEGINNER3 | {"model": {k: v for k, v in _BEGINNER3["model"].items() if k not in ("menu", "raise_cap")}}
    with pytest.raises(SystemExit, match="menu"):  # old = v1, so a tp6 job refuses it
        P.load_resume_result(_pod_result_file(tmp_path, r), "beginner", 3, menu="tp6")


def test_resume_result_keeps_non_default_rules_through_the_chain(tmp_path, no_eval):
    first = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=2, menu="tp6", raise_cap=None)
    assert (first["model"]["menu"], first["model"]["raise_cap"]) == ("tp6", None)
    f = _pod_result_file(tmp_path, first, run_id="9")
    with pytest.raises(SystemExit, match="menu"):
        P.load_resume_result(f, "beginner", 3)
    st, _ = P.load_resume_result(f, "beginner", 3, menu="tp6", raise_cap=None)
    second = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=2, resume=st, menu="tp6", raise_cap=None)
    assert (second["model"]["menu"], second["model"]["raise_cap"]) == ("tp6", None)
    assert second["iters"] > first["iters"] == second["resumed_from"]
