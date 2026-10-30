"""#405: TP-feature ranges from the average-strategy snapshot instead of the current strategy."""
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pytest

from stalker import train_jobs as T
from stalker.e3 import parallel
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import RANGE_EVERY, E3MCCFR
from stalker.tools import pod_train as P


def _sha(m: E3MCCFR) -> str:
    return hashlib.sha256(json.dumps(m.state(), sort_keys=True).encode()).hexdigest()


@pytest.fixture(scope="module")
def pool():
    with ProcessPoolExecutor(2) as p:
        yield p


def test_default_is_current_ranges_with_the_old_checkpoint_layout():
    a, b = E3MCCFR(3, 3, 3), E3MCCFR(3, 3, 3, ranges="current", range_every=1)
    a.iterate(4), b.iterate(4)
    assert a.ranges == "current" and not a.snap and _sha(a) == _sha(b)
    st = a.state()
    assert st["version"] == 1 and not {"ranges", "range_every", "snap", "snap_at"} & st.keys()


def test_seat_probs_read_the_snapshot_rows_in_average_mode():
    def model(ranges):
        m = E3MCCFR(0, 3, 3, ranges=ranges, range_every=1)
        m.regret[K.key("p", 0)] = np.array([1.0, 0.0])    # current strategy: always action 0
        m.avg[K.key("p", 0)] = np.array([1.0, 3.0])       # average strategy: 1/4, 3/4
        m.iterations = 1
        m.refresh_snapshot()
        return m._seat_probs("p", np.array([0, 1, -1]), 2)

    cur, avg = model("current"), model("average")
    assert np.allclose(cur, [[1, 0], [0.5, 0.5], [0, 0]])
    # step 1 has no average row yet, so it falls back to the current strategy (uniform here)
    assert np.allclose(avg, [[0.25, 0.75], [0.5, 0.5], [0, 0]])


def test_snapshot_refreshes_every_range_every_iterations():
    m = E3MCCFR(4, 3, 3, ranges="average", range_every=3)
    seen = []
    for _ in range(7):
        m.iterate(1)
        seen.append(m.snap_at)
    assert seen == [0, 0, 0, 3, 3, 3, 6]
    assert m.snap and all(np.isclose(v.sum(), 1) for v in m.snap.values())


def test_average_ranges_change_training_and_are_seeded():
    cur = E3MCCFR(5, 3, 3)
    a, b = (E3MCCFR(5, 3, 3, ranges="average", range_every=2) for _ in range(2))
    for m in (cur, a, b):
        m.iterate(12)
    assert _sha(a) == _sha(b)
    assert _sha(a) != _sha(cur)


def test_parallel_average_ranges_are_seeded_and_resume_bit_for_bit(pool):
    def fresh():
        return E3MCCFR(7, 3, 3, ranges="average", range_every=3)

    whole, again = fresh(), fresh()
    parallel.iterate(whole, 10, workers=2, batch=1, pool=pool)
    parallel.iterate(again, 10, workers=2, batch=1, pool=pool)
    # syncs every 2 iterations: refreshes at the first sync 3+ iterations after the last one (4, 8)
    assert _sha(whole) == _sha(again) and whole.snap_at == 8
    part = fresh()
    parallel.iterate(part, 6, workers=2, batch=1, pool=pool)   # stops between two refreshes
    assert part.snap and part.snap_at == 4
    resumed = E3MCCFR.from_state(json.loads(json.dumps(part.state())))
    parallel.iterate(resumed, 4, workers=2, batch=1, pool=pool)
    assert _sha(resumed) == _sha(whole)


def test_sequential_checkpoint_keeps_the_snapshot():
    whole = E3MCCFR(8, 3, 3, ranges="average", range_every=2)
    whole.iterate(7)
    part = E3MCCFR(8, 3, 3, ranges="average", range_every=2)
    part.iterate(5)
    st = json.loads(json.dumps(part.state()))
    assert st["version"] == 2 and st["ranges"] == "average" and st["snap_at"] == 4 and st["snap"]
    back = E3MCCFR.from_state(st)
    assert back.state() == part.state()
    back.iterate(2)
    assert _sha(back) == _sha(whole)


def test_bad_options_are_refused():
    with pytest.raises(ValueError, match="ranges"):
        E3MCCFR(0, 3, 3, ranges="mean")
    with pytest.raises(ValueError, match="range_every"):
        E3MCCFR(0, 3, 3, range_every=0)


def test_pod_pack_round_trips_the_snapshot():
    m = E3MCCFR(3, 5, 3, "basic", ranges="average", range_every=2)
    m.iterate(5)
    meta = {"k": m.k, "n": m.n, "depth": m.depth, "iterations": m.iterations, "nodes": m.nodes,
            "menu": m.menu, "raise_cap": m.raise_cap, "rng": m.rng.bit_generator.state,
            "ranges": m.ranges, "range_every": m.range_every, "snap_at": m.snap_at}
    st = P.unpack_state(P.pack(m), meta)
    assert st == json.loads(json.dumps(m.state()))


def test_pod_run_records_the_ranges_and_a_chain_refuses_other_ranges(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "e3_evaluate", lambda m, seed: {"lbr": None})  # the chain, not the evaluation
    r = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=1, ranges="average")
    assert r["model"]["ranges"] == "average" and r["model"]["range_every"] == RANGE_EVERY
    f = tmp_path / "r.json"
    f.write_text(json.dumps(r), encoding="utf-8")
    st, _ = P.load_resume_result(f, "beginner", 3, ranges="average")
    assert E3MCCFR.from_state(st).ranges == "average"
    with pytest.raises(SystemExit, match="ranges"):
        P.load_resume_result(f, "beginner", 3)
    plain = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=1)
    assert "ranges" not in plain["model"]


def test_avgrange_job_is_registered_and_resumable(tmp_path):
    job = "e3-tp-mid-avgrange-w4"
    assert job in T.JOBS and job in T.RESUMABLE
    kw = T.JOBS[job].keywords
    assert (kw["tier"], kw["workers"], kw["ranges"]) == ("mid", 4, "average")
    assert T.JOBS["e3-tp-mid-w4"].keywords.get("ranges", "current") == "current"
    # a current-range checkpoint under the average job's name is refused, not silently continued
    m = E3MCCFR(1, 11, 6, "full")
    (tmp_path / f"{job}-seed1.ckpt.json").write_text(json.dumps(m.state()), encoding="utf-8")
    with pytest.raises(SystemExit, match="ranges"):
        T.JOBS[job](1, 1, tmp_path / "out", resume=tmp_path)
