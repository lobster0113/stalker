import numpy as np
import pytest

from referee.e2 import lbr as L
from stalker.core.cards import cards
from stalker.e2 import game as G
from stalker.e2.eq_view import N, EqMCCFR, EqView, combo_index, eq_buckets, equity_vs, seat_probs

BOARD = tuple(cards("Kc7d2s"))


def _only(hand):
    w = np.zeros(N)
    w[combo_index(tuple(cards(hand)))] = 1
    return w


def test_equity_against_a_known_range_follows_hand_order():
    assert equity_vs(BOARD, _only("KsKd"))[combo_index(tuple(cards("7h7s")))] < 0.15  # set under set
    assert equity_vs(BOARD, _only("4h3h"))[combo_index(tuple(cards("KsKd")))] > 0.85  # 12 sampled runouts
    assert equity_vs((), _only("KsKd"))[combo_index(tuple(cards("AsAd")))] == pytest.approx(0.82, abs=0.03)
    assert np.isnan(equity_vs(BOARD, np.ones(N))).sum() == N - 1176


def test_equity_steps_hold_equal_mass_and_depend_on_the_range():
    b = eq_buckets(BOARD, np.ones(N), 5)
    mass = np.bincount(b[b >= 0], minlength=5) / (b >= 0).sum()
    assert np.all(np.abs(mass - 0.2) < 0.05)
    # Against a range of only sets of kings, almost nothing has equity: the steps reorder.
    assert not np.array_equal(b, eq_buckets(BOARD, _only("KsKd"), 5))


def test_seat_probs_follow_buckets_and_zero_board_collisions():
    s = G.deal(np.random.default_rng(0))
    b = np.zeros(N, dtype=int)
    b[:10] = -1
    pr = seat_probs(lambda k: [0.25, 0.75] if "|0|" in k else None, s, 0, b, 2)
    assert np.all(pr[:10] == 0) and np.allclose(pr[10:], [0.25, 0.75])


def test_eq_mccfr_is_deterministic_and_keys_stay_in_range():
    a, c = EqMCCFR(4, 5), EqMCCFR(4, 5)
    a.iterate(20)
    c.iterate(20)
    assert a.policy() == c.policy() and {int(k.split("|")[2]) for k in a.policy()} <= set(range(5))


def test_lbr_reads_an_equity_policy_through_its_view():
    m = EqMCCFR(2, 5)
    m.iterate(20)
    r1 = L.exploitability_lb(m.policy(), 4, seed=3, view=m.view)
    assert r1 == L.exploitability_lb(m.policy(), 4, seed=3, view=EqView(5))
    assert np.isfinite(r1["lbr_bb"])


def test_runouts_do_not_depend_on_the_process_hash_seed():
    import subprocess
    import sys

    code = ("from stalker.e2.eq_view import equity_vs, N; import numpy as np; from stalker.core.cards import cards;"
            "print(repr(float(np.nansum(equity_vs(tuple(cards('Kc7d2s')), np.ones(N))))))")
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env={**__import__("os").environ, "PYTHONHASHSEED": str(h)}).stdout for h in (1, 2)}
    assert len(outs) == 1 and outs != {""}


def test_compiled_equity_equals_the_numpy_path(monkeypatch):
    from stalker.core import fast_eval as F

    rng = np.random.default_rng(11)
    cases = [(tuple(int(x) for x in rng.permutation(52)[:k]), rng.random(N)) for k in (3, 4, 5) for _ in range(3)]
    fast = [equity_vs(b, w) for b, w in cases]
    monkeypatch.setattr(F, "HAVE_NUMBA", False)
    slow = [equity_vs(b, w) for b, w in cases]
    assert all(np.array_equal(np.nan_to_num(a, nan=-1), np.nan_to_num(s, nan=-1)) for a, s in zip(fast, slow))
