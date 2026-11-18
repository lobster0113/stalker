"""#888: parallel MCCFR workers carry payoff (icm, payouts, lam) and the tournament environment (ante, stage)."""
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import numpy as np
import pytest

from stalker.e3 import game as G
from stalker.e3 import parallel
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR

KW = dict(k=K.TIER_K["beginner"], depth=K.TIER_DEPTH["beginner"])
ICM = dict(payoff="icm", payouts=[0.5, 0.3, 0.2], lam=0.25)


def avg_hash(m: E3MCCFR) -> str:
    h = hashlib.sha256()
    for k in sorted(m.avg):
        v = m.avg[k]
        if v is not None:
            h.update(k.encode() + b"\0" + np.ascontiguousarray(v, dtype="<f8").tobytes())
    return h.hexdigest()


def env_slots(m: E3MCCFR) -> set[str]:
    return {f for k in m.regret if not k.startswith("call|") for f in k.split("|")
            if len(f) == 3 and f[0] == "t" and f[1] in K.STAGES and f[2] in "01"}


@pytest.fixture(scope="module")
def pool():
    with ProcessPoolExecutor(2) as p:
        yield p


@pytest.mark.slow
def test_default_chip_parallel_keeps_the_bits_of_main(pool):
    # Pinned from main b54fbbe3 (before #888) with the same (state, workers=2, batch=3, 24 iterations).
    m = E3MCCFR(11, 3, 3)
    parallel.iterate(m, 24, workers=2, batch=3, pool=pool)
    assert m.regret_hash() == "aa247dad17793916463a872d6fe695a5043be5a66a9800b8a795a202b2199cf6"
    c1 = E3MCCFR(11, 3, 3, key_variant="c1")
    parallel.iterate(c1, 24, workers=2, batch=3, pool=pool)
    assert c1.regret_hash() == "a200719db4134104eefa18f4fa696da8d7107f861cd7c9e5b0c0be9d87dcb5c0"


def test_icm_parallel_is_deterministic(pool):
    a, b = E3MCCFR(5, n=3, **KW, **ICM), E3MCCFR(5, n=3, **KW, **ICM)
    parallel.iterate(a, 6, workers=2, batch=2, pool=pool)
    parallel.iterate(b, 6, workers=2, batch=2, pool=pool)
    assert a.regret and a.regret_hash() == b.regret_hash() and avg_hash(a) == avg_hash(b)
    chip = E3MCCFR(5, n=3, **KW)
    parallel.iterate(chip, 6, workers=2, batch=2, pool=pool)
    assert chip.regret_hash() != a.regret_hash(), "icm and chip runs must differ: the payoff reached the workers"


def test_icm_preset_reaches_the_workers(pool):
    m = E3MCCFR(5, n=3, payoff="icm", payouts="6max_sng_wta", **KW)
    parallel.iterate(m, 2, workers=2, batch=1, pool=pool)
    assert m.iterations == 2 and m.regret


def test_worker_models_carry_the_parents_payoff(monkeypatch):
    seen = []

    class Spy(E3MCCFR):
        def iterate(self, iters=1):
            seen.append((self.payoff, self.payouts, self.lam, self.ante, self.stage))
            super().iterate(iters)

    monkeypatch.setattr(parallel, "E3MCCFR", Spy)
    m = E3MCCFR(2, n=3, **KW, payoff="icm", payouts=[3, 2, 1], lam=0.4)
    with ThreadPoolExecutor(1) as one:   # in-process so the spy sees the worker models
        parallel.iterate(m, 4, workers=2, batch=2, pool=one)
    assert m.payouts == (0.5, 2 / 6, 1 / 6)
    assert seen == [("icm", m.payouts, 0.4, 0, "c")] * 2


@pytest.mark.slow
def test_ante_stage_parallel_keys_carry_only_the_ante_slot(pool):
    m = E3MCCFR(3, n=3, key_variant="c1", ante=G.BB, stage="b", **KW)
    parallel.iterate(m, 4, workers=2, batch=2, pool=pool)
    assert m.regret and env_slots(m) == {"tb1"}
    ante = E3MCCFR(3, n=3, key_variant="c1", ante=G.BB, **KW)
    parallel.iterate(ante, 4, workers=2, batch=2, pool=pool)
    assert env_slots(ante) == {"tc1"}


@pytest.mark.slow
def test_icm_ante_checkpoint_continues_bit_for_bit(pool):
    kw = dict(n=3, key_variant="c1", ante=G.BB, stage="b", **KW, **ICM)
    whole = E3MCCFR(7, **kw)
    parallel.iterate(whole, 6, workers=2, batch=2, pool=pool)
    part = E3MCCFR(7, **kw)
    parallel.iterate(part, 4, workers=2, batch=2, pool=pool)
    st = json.loads(json.dumps(part.state()))
    resumed = E3MCCFR.from_state(st, payoff="icm", ante=G.BB, stage="b")
    assert (resumed.payoff, resumed.payouts, resumed.lam, resumed.ante, resumed.stage) == \
        (whole.payoff, whole.payouts, whole.lam, whole.ante, whole.stage)
    parallel.iterate(resumed, 2, workers=2, batch=2, pool=pool)
    assert resumed.regret_hash() == whole.regret_hash() and avg_hash(resumed) == avg_hash(whole)
