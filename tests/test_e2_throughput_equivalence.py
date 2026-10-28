"""#201: the throughput changes must not change results. The tree walk keeps main's infoset keys,
payoffs and sampling draws, and the rank-pair strength kernel keeps the board tables bit-identical."""
import numpy as np
import pytest

from stalker.core import fast_eval as F
from stalker.e2 import abstraction as A
from stalker.e2 import game as G
from stalker.e2.abstraction import TIERS
from stalker.e2.mccfr import MCCFR, _sample, infoset


class _Reference(MCCFR):
    """The walk as it was before #201: keys from `infoset`, `G.apply`, `G.payoff`, `rng.choice`, no caches."""

    def _walk(self, s, trav, hk=""):
        if s.done:
            v = G.payoff(s) / G.BB
            return v if trav == 0 else -v
        acts = G.legal(s)
        key = infoset(s, self.abstraction)
        sigma = self._regret_matching(key, len(acts))  # no strategy cache
        if s.to_act == trav:
            vals = np.array([self._walk(G.apply(s, a), trav) for a in acts])
            v = float(sigma @ vals)
            r = self.regret.setdefault(key, np.zeros(len(acts)))
            np.maximum(r + (vals - v), 0, out=r)
            return v
        a = self.rng.choice(len(acts), p=sigma)
        avg = self.avg[key]
        self.avg[key] = (avg if avg is not None else 0) + self.iterations * sigma
        return self._walk(G.apply(s, acts[a]), trav)


@pytest.mark.parametrize("tier", ["baseline", "beginner"])
def test_fast_walk_equals_the_reference_walk(tier):
    fast, ref = MCCFR(11, TIERS[tier]), _Reference(11, TIERS[tier])
    fast.iterate(150)
    ref.iterate(150)
    assert fast.policy() == ref.policy() and len(fast.policy()) > 300
    assert fast.regret.keys() == ref.regret.keys()
    assert all(np.array_equal(fast.regret[k], ref.regret[k]) for k in ref.regret)
    assert fast.rng.bit_generator.state == ref.rng.bit_generator.state


def test_sample_draws_what_rng_choice_draws():
    src = np.random.default_rng(5)
    for _ in range(3000):
        n = int(src.integers(1, 6))
        p = src.random(n) * (src.random(n) > 0.3)
        p = p / p.sum() if p.sum() > 0 else np.full(n, 1.0 / n)
        seed = int(src.integers(1 << 30))
        a, b = np.random.default_rng(seed), np.random.default_rng(seed)
        assert _sample(a, p) == b.choice(n, p=p)
        assert a.bit_generator.state == b.bit_generator.state


def test_step_and_showdown_payoff_equal_apply_and_payoff():
    rng = np.random.default_rng(9)
    for _ in range(300):
        s = G.deal(rng)
        sd = G.showdown(s)
        while not s.done:
            acts = G.legal(s)
            a = acts[int(rng.integers(len(acts)))]
            s2 = G.step(s, a)
            assert s2 == G.apply(s, a)
            s = s2
        assert G.payoff(s, sd) == G.payoff(s)


def _kernel_table(board, kernel):
    """ehs_table's kernel branch with a given kernel function (compiled or its plain-Python body)."""
    rng = np.random.default_rng([20261027, *board])
    live = np.array([c for c in range(52) if c not in board])
    ok = ~np.isin(A.COMBO_ARR, list(board)).any(axis=1)
    need = 5 - len(board)
    runs = A.RUNOUTS if need else 1
    fulls = np.array([np.concatenate([board, rng.choice(live, size=need, replace=False)]) for _ in range(runs)],
                     dtype=np.int64)
    acc = np.zeros(len(A.COMBOS))
    kernel(A.COMBO_ARR, ok, fulls, acc, F._SH, F._POP, F._HI, F._KICK5, F._KICK3, F._KICK2, F._CAT)
    return acc


def _random_boards():
    rng = np.random.default_rng(201)
    return [tuple(int(x) for x in rng.permutation(52)[:k]) for k in (3, 4, 5) for _ in range(6)]


# Flush-heavy boards (3, 4, 5 of a suit), paired boards, straights: the kernel's rank-pair shortcut must
# fall back to full evaluation exactly where a flush is possible.
_BOARDS = [(0, 4, 8), (0, 4, 8, 12), (0, 4, 8, 12, 16), (48, 44, 40, 36, 1), (1, 2, 3, 5, 6),
           (0, 1, 2, 3), (8, 9, 30, 31, 51), (0, 17, 34), (5, 22, 47, 12), (3, 7, 11, 2, 6)] + _random_boards()


@pytest.mark.parametrize("board", _BOARDS)
def test_rank_pair_kernel_equals_the_numpy_table(monkeypatch, board):
    # Plain Python body where numba compiled it (py_func), so CI and local runs check the same logic.
    kernel = getattr(F._rank_runouts, "py_func", F._rank_runouts)
    monkeypatch.setattr(F, "HAVE_NUMBA", False)
    A.ehs_table.cache_clear()
    numpy_path = A.ehs_table(board)
    A.ehs_table.cache_clear()
    one = _kernel_table(board, kernel)
    acc = one
    if len(board) == 5:  # as ehs_table: the one river evaluation summed RUNOUTS times
        acc = np.zeros_like(one)
        for _ in range(A.RUNOUTS):
            acc += one
    got = acc / A.RUNOUTS
    got[np.isnan(numpy_path)] = np.nan
    assert np.array_equal(got, numpy_path, equal_nan=True)
