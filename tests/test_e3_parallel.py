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
