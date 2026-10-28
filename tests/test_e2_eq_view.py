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
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8",
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


def test_range_equity_kernel_path_equals_the_numpy_path(monkeypatch):
    # #237 review rule: the kernel runs as plain Python without numba, so CI checks its logic too.
    import numpy as np

    from stalker.core import fast_eval as F
    from stalker.e2.eq_view import equity_vs

    rng = np.random.default_rng(188)
    for board in [(0, 17, 34), (5, 22, 47, 12)]:
        w = rng.random(1326) * (rng.random(1326) > 0.3)
        monkeypatch.setattr(F, "HAVE_NUMBA", True)
        kernel = equity_vs(board, w)
        monkeypatch.setattr(F, "HAVE_NUMBA", False)
        numpy_path = equity_vs(board, w)
        assert np.array_equal(kernel, numpy_path, equal_nan=True)


# #244 review: the static view must keep the pre-PR LBR numbers. Golden values from main ae8b068
# (`exploitability_lb({}, 20, seed=3)` and the 30-iteration MCCFR(5) policy below).
GOLDEN_UNIFORM = {"lbr_bb": 0.3887, "stderr_bb": 2.0384, "seat0_bb": -1.1475, "seat1_bb": 1.925, "hands": 20}
GOLDEN_TRAINED = {"lbr_bb": 0.095, "stderr_bb": 2.1127, "seat0_bb": -2.4225, "seat1_bb": 2.6125, "hands": 20}


def test_static_view_reproduces_the_pre_pr_lbr_exactly():
    from referee.e2.lbr import StaticView, exploitability_lb
    from stalker.e2.abstraction import BASELINE
    from stalker.e2.mccfr import MCCFR

    m = MCCFR(5)
    m.iterate(30)
    pol = m.policy()
    for policy, golden in (({}, GOLDEN_UNIFORM), (pol, GOLDEN_TRAINED)):
        assert exploitability_lb(policy, 20, seed=3) == golden
        assert exploitability_lb(policy, 20, seed=3, view=StaticView(BASELINE)) == golden


class _Recorder:
    """Wraps EqMCCFR._walk_r to keep every node's (state, ranges)."""

    def __init__(self, m):
        self.nodes, orig = [], m._walk_r

        def walk(s, ranges, trav):
            self.nodes.append((s, ranges[0].copy(), ranges[1].copy()))
            return orig(s, ranges, trav)

        m._walk_r = walk


def test_public_ranges_stay_valid_and_reproducible():
    import numpy as np

    from stalker.e2.eq_view import EqMCCFR, _board_dead

    runs = []
    for _ in range(2):
        m = EqMCCFR(7, 5)
        rec = _Recorder(m)
        m.iterate(6)
        runs.append(rec.nodes)
    a, b = runs
    assert len(a) == len(b) and all(np.array_equal(x[1], y[1]) and np.array_equal(x[2], y[2]) for x, y in zip(a, b))
    checked = 0
    for s, r0, r1 in a:
        for r in (r0, r1):
            assert np.isfinite(r).all() and (r >= 0).all() and r.sum() > 0
            assert np.isclose((r / r.sum()).sum(), 1.0)
        if s.board and s.history and s.history[-1] != "/" and not s.done:
            q = 1 - s.to_act                                  # acted last, on this street
            assert ((r0, r1)[q][_board_dead(tuple(s.board))] == 0).all()
            checked += 1
    assert checked > 0
