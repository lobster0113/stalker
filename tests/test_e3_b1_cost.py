"""b1 next-card equities (#454): the batched path must give the same buckets as the per-card reference (kernel logic run as plain Python, which is slow: few cases)."""
from types import SimpleNamespace

import numpy as np
import pytest

from stalker.core.cards import cards
from stalker.e3 import cost_probe
from stalker.e3 import tp_key as K


def _reference_outs_vuln(s, seat, ranges):
    """hand_outs_vuln before #454: one `_multi_eq` per next card."""
    board = tuple(s.board)
    opps = [q for q in s.live() if q != seat]
    now = K._multi_eq(board, opps, ranges)
    pair = np.array(K.COMBOS)
    free = np.ones(K.N_CARDS)
    for q in opps:
        mass = ranges[q] * ~np.isnan(K._equity_cached(board, K._UNIFORM))
        by_card = np.zeros(K.N_CARDS)
        np.add.at(by_card, pair[:, 0], mass)
        np.add.at(by_card, pair[:, 1], mass)
        free = free * (1.0 - by_card / mass.sum() if mass.sum() > 0 else 1.0)
    cs = [c for c in range(K.N_CARDS) if c not in board]
    gain = np.stack([K._multi_eq(board + (c,), opps, ranges) for c in cs]) - now[None, :]
    w = free[cs][:, None] * ~np.isnan(gain)
    total = w.sum(axis=0)
    ok = (total > 0) & ~np.isnan(now)
    g = np.nan_to_num(gain)
    den = np.where(ok, total, 1.0)
    return (np.where(ok, 100.0 * (w * (g >= K.OUT_GAIN)).sum(axis=0) / den, np.nan),
            np.where(ok, 100.0 * (w * (g <= -K.OUT_GAIN)).sum(axis=0) / den, np.nan))


def _situations(count, seed=7):
    rng = np.random.default_rng(seed)
    deck = np.arange(52)
    for i in range(count):
        n_board = 3 + i % 2
        board = tuple(int(c) for c in rng.choice(deck, n_board, replace=False))
        live = [0] + sorted(int(q) for q in rng.choice(np.arange(1, 6), 1 + i % 3, replace=False))
        ranges = [rng.random(K.N) ** 3 * (rng.random(K.N) < 0.5 + 0.5 * rng.random()) for _ in range(6)]
        yield SimpleNamespace(street=n_board - 2, board=board, live=lambda live=live: live), ranges


def _clear_caches():
    K._NEXT_CACHE.clear()
    K._EQ_CACHE.clear()


def _check(count, monkeypatch):
    # CI has no numba: force the kernel branch (plain Python) for the new path, per-card numpy for the reference,
    # so `_next_card_eq`'s equity_segments loop is really exercised and not compared with itself.
    from stalker.core import fast_eval

    depths = ("basic", "pro", "full")
    for i, (s, ranges) in enumerate(_situations(count)):
        with monkeypatch.context() as m:
            m.setattr(fast_eval, "HAVE_NUMBA", True)
            _clear_caches()
            new = K.hand_outs_vuln(s, 0, ranges)
            code = K.b1_code(s, 0, ranges, depths[i % 3])
        with monkeypatch.context() as m:
            m.setattr(fast_eval, "HAVE_NUMBA", False)
            _clear_caches()
            ref = _reference_outs_vuln(s, 0, ranges)
            m.setattr(K, "hand_outs_vuln", _reference_outs_vuln)
            ref_code = K.b1_code(s, 0, ranges, depths[i % 3])
        for x, y in zip(new, ref):
            np.testing.assert_array_equal(x, y)
        np.testing.assert_array_equal(code, ref_code)


def test_batched_next_card_equities_match_the_per_card_reference(monkeypatch):
    _check(3, monkeypatch)


@pytest.mark.slow
def test_kernel_path_matches_per_card_on_40_flop_and_turn_situations(monkeypatch):
    _check(40, monkeypatch)


def test_cost_probe_reports_a_positive_cost_per_iteration():
    assert cost_probe.seconds_per_iter("b1", iters=1, k=5, n=3, depth="basic") > 0
