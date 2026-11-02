import hashlib
import json
from concurrent.futures import ProcessPoolExecutor

import pytest

from stalker import train_jobs as T
from stalker.e3 import parallel
from stalker.e3.mccfr import E3MCCFR


def _sha(m: E3MCCFR) -> str:
    return hashlib.sha256(json.dumps(m.state(), sort_keys=True).encode()).hexdigest()


@pytest.fixture(scope="module")
def pool():
    with ProcessPoolExecutor(2) as p:
        yield p


def test_one_worker_is_the_sequential_chain():
    a, b = E3MCCFR(3, 3, 3), E3MCCFR(3, 3, 3)
    a.iterate(4)
    parallel.iterate(b, 4, workers=1)
    assert _sha(a) == _sha(b)


def test_same_workers_and_batch_give_the_same_bits(pool):
    a, b = E3MCCFR(5, 3, 3), E3MCCFR(5, 3, 3)
    parallel.iterate(a, 5, workers=2, batch=2, pool=pool)
    parallel.iterate(b, 5, workers=2, batch=2, pool=pool)
    assert _sha(a) == _sha(b)
    assert a.iterations == 5 and a.regret and a.policy()
    assert sum(a.visits.values()) > 0 and a.nodes > 0


def test_checkpoint_continues_bit_for_bit(pool):
    whole = E3MCCFR(7, 3, 3)
    parallel.iterate(whole, 6, workers=2, batch=2, pool=pool)
    part = E3MCCFR(7, 3, 3)
    parallel.iterate(part, 4, workers=2, batch=2, pool=pool)
    resumed = E3MCCFR.from_state(json.loads(json.dumps(part.state())))
    parallel.iterate(resumed, 2, workers=2, batch=2, pool=pool)
    assert _sha(resumed) == _sha(whole)


def test_merged_regrets_stay_non_negative(pool):
    m = E3MCCFR(9, 3, 3)
    parallel.iterate(m, 4, workers=2, batch=1, pool=pool)
    assert all((r >= 0).all() for r in m.regret.values())


def test_split_and_bad_arguments():
    assert parallel.split(5, 2) == [3, 2] and parallel.split(1, 4) == [1, 0, 0, 0]
    with pytest.raises(ValueError, match="workers"):
        parallel.iterate(E3MCCFR(0, 3, 3), 1, workers=0)


def test_w4_jobs_are_registered_and_resumable():
    for job in ("e3-tp-beginner-w4", "e3-tp-mid-w4"):
        assert job in T.JOBS and job in T.RESUMABLE
        assert T.JOBS[job].keywords["workers"] == 4


def test_9_handed_jobs_are_registered_and_resumable():
    for job in ("e3-tp-beginner9-w4", "e3-tp-mid9-w4"):
        assert job in T.JOBS and job in T.RESUMABLE
        assert T.JOBS[job].keywords["players"] == 9 and T.JOBS[job].keywords["workers"] == 4


def test_9_handed_parallel_is_deterministic(pool):
    a, b = E3MCCFR(2, 3, 9), E3MCCFR(2, 3, 9)
    parallel.iterate(a, 4, workers=2, batch=2, pool=pool)
    parallel.iterate(b, 4, workers=2, batch=2, pool=pool)
    assert _sha(a) == _sha(b) and a.regret


def test_flat_regret_transfer_keeps_the_bits_of_the_dict_transfer(pool):
    # #513: pinned from main before the flat-array transfer (3 workers, batch 5, 60 iterations).
    m = E3MCCFR(5, 3, 3)
    with ProcessPoolExecutor(3) as p:
        parallel.iterate(m, 60, workers=3, batch=5, pool=p)
    assert m.regret_hash() == "e9645be1f6259b858067c5ea98c2228e7af1d12476c7af751e1f41e57a8eaadd"


def test_worker_regret_view_copies_only_updated_rows():
    import numpy as np
    reg = {f"k{i}": np.arange(3.0) + i for i in range(5)}
    ov = parallel._Overlay(*parallel.pack_regret(reg))
    assert (ov.get("k2") == reg["k2"]).all() and ov.get("zz") is None and not dict.keys(ov)
    row = ov.setdefault("k2", np.zeros(3))
    row += 1
    assert (ov.get("k2") == reg["k2"] + 1).all() and (ov.base("k2") == reg["k2"]).all()
    assert (ov.setdefault("new", np.ones(2)) == 1).all() and set(dict.keys(ov)) == {"k2", "new"}


def test_worker_table_memory_per_key_is_small():
    # #513 regression: 10^5 keys of 5 actions. The old worker held pickle.loads(blob) plus a copy of
    # every row (~1.7 KB/key measured in the pod job); the flat view must stay under 400 bytes/key
    # (measured ~200 locally: key str + dict slot + int; rows live in one float64 array).
    import pickle
    import tracemalloc
    import numpy as np
    n = 100_000
    blob = pickle.dumps(parallel.pack_regret({f"s{i:08d}|1.2.3": np.full(5, float(i)) for i in range(n)}))
    tracemalloc.start()
    ov = parallel._Overlay(*pickle.loads(blob))
    used = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    assert len(ov.rows) == n and used / n < 400, f"{used / n:.0f} bytes/key; keep the worker table flat"


def test_flat_average_snapshot_keeps_the_bits():
    # #513: the average-range snapshot also crosses as a flat array; hash pinned from main (ranges=average).
    m = E3MCCFR(5, 3, 3, ranges="average", range_every=10, avg_rule="own")
    with ProcessPoolExecutor(3) as p:
        parallel.iterate(m, 90, workers=3, batch=5, pool=p)
    assert m.regret_hash() == "13aca73d5d5afc4512ea79c18fb7c25cd14ebe732f712634b1e29fe8861dde6a"
