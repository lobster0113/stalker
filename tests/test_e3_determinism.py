"""E3 results must not depend on the runner's CPU (#447): same seed, same table, bit for bit."""
import numpy as np
import pytest

from stalker.e3 import parallel
from stalker.e3.mccfr import E3MCCFR
from stalker.tools import e3_determinism as D


def test_regret_hash_covers_keys_and_bits_but_not_insertion_order():
    m = E3MCCFR(1, 5, 3, "basic")
    m.iterate(3)
    h = m.regret_hash()
    assert len(h) == 64 and h == m.regret_hash()
    m.regret = dict(reversed(list(m.regret.items())))
    assert m.regret_hash() == h
    assert E3MCCFR.from_state(m.state()).regret_hash() == h       # checkpoints (#301) keep the hash
    k = next(k for k, r in m.regret.items() if r.any())
    m.regret[k] = m.regret[k].copy()
    m.regret[k][np.argmax(m.regret[k])] = np.nextafter(m.regret[k].max(), np.inf)   # one ulp
    assert m.regret_hash() != h


def test_parallel_run_hash_is_reproducible_in_process():
    a, b = (E3MCCFR(2, 5, 3, "basic") for _ in range(2))
    for m in (a, b):
        parallel.iterate(m, 8, workers=2, batch=2)
    assert a.regret_hash() == b.regret_hash()


def test_e3_fingerprint_is_identical_under_emulated_runners():
    # Each setting is a fresh process with another BLAS kernel/thread count or numpy SIMD level.
    # Before #447 the OpenBLAS kernels changed the preflop equity bits, and Prescott's dot also the regrets.
    results = {name: D.run_setting(env, "beginner", 6, 12, 2, 1, 6, timeout=120)
               for name, env in D.settings(numba_off=False).items()}
    assert not D.compare(results), "\n".join(D.compare(results))


def test_e3_fingerprint_is_identical_with_numba_disabled():
    pytest.importorskip("numba")   # without numba both runs are the numpy path anyway
    on = D.run_setting({}, "beginner", 3, 2, 2, 1, 2, timeout=120)
    off = D.run_setting({"NUMBA_DISABLE_JIT": "1"}, "beginner", 3, 2, 2, 1, 2, timeout=120)
    assert not D.compare({"default": on, "numba-off": off})
