"""c1 per-iteration cost (#499): `_next_card_eq` caches by range values, so the walks of one deal reuse rows
that an object-keyed cache recomputed; the learned table must not change by a bit."""
import numpy as np
import pytest

from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR


def _object_keyed(board, w, cards, _cache={}):
    """`_next_card_eq` before #499: cached per (board, range object), computed by the same code."""
    key = (board, id(w))
    hit = _cache.get(key)
    if hit is not None and hit[0] is w:
        return hit[1]
    K._NEXT_CACHE.clear()   # force the real function to compute, never to answer from its own cache
    out = _REAL(board, w, cards)
    if len(_cache) >= 64:
        _cache.clear()
    _cache[key] = (w, out)
    return out


_REAL = K._next_card_eq


def _c1(iters):
    m = E3MCCFR(3, K.TIER_K["mid"], 6, K.TIER_DEPTH["mid"], "real", None, "average", avg_rule="own",
                key_variant="c1", stacks="sampled")
    m.iterate(iters)
    return m


def test_equal_values_in_a_new_array_hit_the_cache(monkeypatch):
    K._NEXT_CACHE.clear()
    calls = []
    monkeypatch.setattr(K, "equity_vs", lambda board, w: calls.append(1) or np.full(K.N, 0.5))
    monkeypatch.setattr(K.fast_eval, "HAVE_NUMBA", False)
    board, cards = (0, 5, 10), [20, 30]
    w = np.random.default_rng(1).random(K.N)
    first = K._next_card_eq(board, w, cards)
    assert len(calls) == 2
    assert K._next_card_eq(board, w.copy(), cards) is first and len(calls) == 2   # same values: no work
    w2 = w.copy()
    w2[7] += 1e-12
    K._next_card_eq(board, w2, cards)
    assert len(calls) == 4                                                        # one bit apart: computed
    K._next_card_eq((0, 5, 11), w, cards)
    assert len(calls) == 6                                                        # other board: computed
    K._NEXT_CACHE.clear()


@pytest.mark.slow
def test_c1_training_bits_match_the_object_keyed_cache(monkeypatch):
    K._NEXT_CACHE.clear()
    new = _c1(6)
    assert any(len(b) in (3, 4) for (b, _) in K._NEXT_CACHE) or new.iterations == 6
    with monkeypatch.context() as m:
        m.setattr(K, "_next_card_eq", _object_keyed)
        old = _c1(6)
    assert len(new.regret) == len(old.regret) and set(new.regret) == set(old.regret)
    assert new.regret_hash() == old.regret_hash()
