"""Vector-CFR oracle for the TP-merged regret update (#414): exact tree vs vector form vs the E3 sampler."""
import copy

import numpy as np
import pytest

from referee.anchors.toy import expected_value, exploitability, kuhn, leduc
from stalker.core.cards import cards
from stalker.toy import bottleneck as b
from stalker.vcfr import sampled as SM
from stalker.vcfr import solver as S
from stalker.vcfr import toy as T
from stalker.vcfr.river import RiverGame

GAMES = {"kuhn": (kuhn.game, T.kuhn_public), "leduc": (leduc.game, T.leduc_public)}
# Merges: kuhn_key(2) puts J and Q in one key; leduc_key(3, 1) merges every private rank on a board, so a
# paired card (one of its rank left, half the deals) shares a key with an unpaired one; leduc_key(2, 2)
# merges in both rounds.
MERGED = [("kuhn", b.kuhn_key(2)), ("leduc", b.leduc_key(3, 1)), ("leduc", b.leduc_key(2, 2))]
CASES = [("kuhn", T.identity), ("leduc", T.identity)] + MERGED
BOARD = tuple(cards(S.DEFAULT_BOARD))


@pytest.fixture(scope="module")
def trees():
    return {g: (full(), pub()) for g, (full, pub) in GAMES.items()}


def _both(root, proot, key, sigma):
    """(a) and (b) increments of both passes under one frozen strategy, as flat vectors."""
    info = T.keys(root, key)
    v = T.VectorCFR(proot, key)
    a = T.flat(info, [T.exact_update(root, key, sigma, p) for p in (0, 1)])
    bb = T.flat(info, [tuple(v.to_table(x) for x in v.update(p, v.from_table(sigma))) for p in (0, 1)])
    return a, bb


@pytest.mark.parametrize("game,key", CASES)
def test_vector_form_update_equals_full_tree_update(trees, game, key):
    root, proot = trees[game]
    assert set(T.VectorCFR(proot, key).ids) == set(T.keys(root, key))
    a, bb = _both(root, proot, key, T.random_sigma(root, key, np.random.default_rng(1)))
    assert np.abs(a).max() > 0.1 and np.allclose(a, bb, rtol=0, atol=1e-12)


@pytest.mark.parametrize("game,key", CASES)
def test_exact_and_vector_cfr_runs_agree(trees, game, key):
    root, proot = trees[game]
    a, v = T.ExactCFR(root, key), T.VectorCFR(proot, key)
    a.iterate(15)
    v.iterate(15)
    for name in ("regret", "avg"):
        tb = v.to_table(getattr(v, name))
        assert all(np.allclose(getattr(a, name)[k], tb[k], rtol=1e-12, atol=1e-12) for k in tb)


def test_kuhn_reaches_the_game_value(trees):
    root, proot = trees["kuhn"]
    a, v = T.ExactCFR(root), T.VectorCFR(proot)
    a.iterate(1000)
    v.iterate(1000)
    sa, sv = a.average_strategy(), v.average_strategy()
    assert expected_value(root, sa) == pytest.approx(kuhn.GAME_VALUE, abs=1e-4)   # -1/18
    assert exploitability(root, sa) < 1e-3
    assert max(np.abs(np.subtract(sa[k], sv[k])).max() for k in sa) < 1e-12


def _swap_extremes(table, rows, w, d):
    # Mutation: inside each key, the infosets with the largest and smallest reach trade weights.
    w = w.copy()
    for r in np.unique(rows):
        idx = np.flatnonzero(rows == r)
        if len(idx) > 1:
            hi, lo = idx[np.argmax(w[idx])], idx[np.argmin(w[idx])]
            w[hi], w[lo] = w[lo], w[hi]
    np.add.at(table, rows, w[:, None] * d)


# Kuhn's J-Q merge is left out: both cards face the same opponent mix, so their reaches are always equal.
@pytest.mark.parametrize("game,key", MERGED[1:])
def test_reach_swap_between_merged_infosets_is_caught(trees, monkeypatch, game, key):
    root, proot = trees[game]
    sigma = T.random_sigma(root, key, np.random.default_rng(2))
    monkeypatch.setattr(T, "scatter_regret", _swap_extremes)
    a, bb = _both(root, proot, key, sigma)
    assert np.linalg.norm(a - bb) > 0.05 * np.linalg.norm(a)


@pytest.mark.parametrize("game,key,n", [("kuhn", b.kuhn_key(2), 6400), ("leduc", b.leduc_key(3, 1), 1600)])
def test_e3_sampler_mean_converges_to_the_exact_update(trees, game, key, n):
    curve = T.noise_curve(trees[game][0], key, (n // 16, n), seed=1)
    first, last = curve[0]["rel_err"], curve[-1]["rel_err"]
    assert last < 0.12 and last < 0.5 * first       # about 1/sqrt(n): 16x the samples, 1/4 the error


def test_sampling_correction_mutation_is_caught(trees):
    root, key = trees["leduc"][0], b.leduc_key(3, 1)
    off = {"explore": 0.5, "uniform_chance": True}
    good = T.noise_curve(root, key, (1600,), seed=1, **off)[0]["rel_err"]
    bad = T.noise_curve(root, key, (1600,), seed=1, correct=False, **off)[0]["rel_err"]
    assert good < 0.2 and bad > 2 * good


def test_two_player_e3_average_weight_is_own_reach(trees):
    root, key = trees["leduc"][0], b.leduc_key(2, 2)
    sigma = T.random_sigma(root, key, np.random.default_rng(3))
    for p in (0, 1):
        own, e3 = T.exact_update(root, key, sigma, p), T.exact_update(root, key, sigma, p, avg_reach="e3")
        assert all(np.allclose(own[1][k], e3[1][k], rtol=0, atol=1e-15) for k in own[1])


def test_three_player_e3_average_weight_is_not_own_reach():
    # Pinned finding (#414): with more than two players, E3's legacy rule adds sigma to the average at every
    # visit of a non-traverser's node, so in expectation the weight is pi_c pi_-traverser (the other
    # opponents' reach included), not pi_c pi_i. The sampler matches the first and misses the second.
    # avg_rule="own" fixes it (#426, next test); legacy stays for the runs made with it.
    root = T.kuhn3()
    e3 = T.noise_curve(root, T.identity, (1600,), seed=1, n_players=3, avg_reach="e3")[0]["rel_err"]
    own = T.noise_curve(root, T.identity, (1600,), seed=1, n_players=3, avg_reach="own")[0]["rel_err"]
    assert e3 < 0.1 and own > 3 * e3
    # The ratio is not one constant per key, so it reweights iterations in the average strategy.
    rng = np.random.default_rng(4)
    ratios = []
    for _ in range(2):
        sigma = T.random_sigma(root, T.identity, rng)
        o, e = T.exact_update(root, T.identity, sigma, 0, 3)[1], T.exact_update(root, T.identity, sigma, 0, 3, "e3")[1]
        ratios.append({k: e[k].sum() / o[k].sum() for k in o})
    assert max(abs(ratios[0][k] - ratios[1][k]) for k in ratios[0]) > 0.1


def test_three_player_own_avg_rule_converges_to_own_reach():
    # #426: dividing out the other sampled opponents' reach makes the sampler's average unbiased for
    # pi_c pi_i: the error falls as 1/sqrt(n) against "own", and the "e3" target is now the one missed.
    root = T.kuhn3()
    own = T.noise_curve(root, T.identity, (400, 6400), seed=1, n_players=3, avg_reach="own", avg_rule="own")
    assert own[-1]["rel_err"] < 0.08 and own[-1]["rel_err"] < 0.5 * own[0]["rel_err"]
    e3 = T.noise_curve(root, T.identity, (1600,), seed=1, n_players=3, avg_reach="e3", avg_rule="own")[0]
    assert e3["rel_err"] > 0.3


@pytest.mark.parametrize("game,key", [("kuhn", b.kuhn_key(2)), ("leduc", b.leduc_key(3, 1))])
def test_two_player_avg_rules_are_the_same_sample(trees, game, key):
    # Heads-up the divisor is empty, so the two rules make the same increments from the same draws, hence
    # the same expected average weight (test_two_player_e3_average_weight_is_own_reach).
    root = trees[game][0]
    sigma = T.random_sigma(root, key, np.random.default_rng(5))
    legacy, own = T.E3Sampler(root, key), T.E3Sampler(root, key, avg_rule="own")
    r1, r2 = np.random.default_rng(6), np.random.default_rng(6)
    for _ in range(200):
        for p in (0, 1):
            a, o = legacy.sample(sigma, p, r1), own.sample(sigma, p, r2)
            assert all(t1.keys() == t2.keys() and all(np.array_equal(t1[k], t2[k]) for k in t1)
                       for t1, t2 in zip(a, o))


def test_e3_sampler_rejects_unknown_avg_rule(trees):
    with pytest.raises(ValueError):
        T.E3Sampler(trees["kuhn"][0], avg_rule="x")


def test_exact_update_rejects_unknown_avg_reach(trees):
    root = trees["kuhn"][0]
    with pytest.raises(ValueError):
        T.exact_update(root, T.identity, T.random_sigma(root, T.identity, np.random.default_rng(0)), 0, avg_reach="x")


@pytest.fixture(scope="module")
def river():
    out = {}
    for name, ranges in (("uniform", None), ("skewed", SM.skewed_ranges(BOARD))):
        g = RiverGame(BOARD, stack=1.0, bets=(1.0,), raises=(), raise_cap=2, ranges=ranges)
        m = S.VectorCFR(g, S.tp_keyer(5), key_ranges="initial")
        m.iterate(10)
        out[name] = m
    return out


@pytest.mark.parametrize("ranges", ["uniform", "skewed"])
def test_vector_cfr_pass_is_the_intended_update(river, ranges):
    # Regression (#414): with non-uniform ranges the TP scatter must weight each combo by its own range,
    # and the average by its live opponent mass, or merged combos count as if equally likely.
    m = copy.deepcopy(river[ranges])
    for t in m.regret.values():
        t += 1e6                       # far from the CFR+ floor, so one pass's increment is visible
    g = m.game
    z = float(g.init[0] @ g.sd.card_mass(g.init[1]))
    for p in (0, 1):
        reg, _ = SM.expected_update(m, p)
        avg = SM.expected_update(m, 1 - p)[1]        # p's average is accumulated in the other pass
        w = copy.deepcopy(m)
        w.t += 1
        w._walk(g.root, p, list(g.init))
        for tid, x in reg.items():
            assert np.allclose((w.regret[tid] - m.regret[tid]) / z, x, rtol=0, atol=1e-9)
        for tid, x in avg.items():
            assert np.allclose((w.avg[tid] - m.avg.get(tid, 0)) / (w.t * z), x, rtol=0, atol=1e-12)


def test_river_sampler_mean_converges_to_the_oracle(river):
    curve = SM.noise_curve(river["skewed"], (250, 4000), seed=1)
    assert curve[-1]["rel_err"] < 0.06 and curve[-1]["rel_err"] < 0.5 * curve[0]["rel_err"]


def test_river_oracle_needs_fixed_keys():
    g = RiverGame(BOARD, stack=1.0, bets=(1.0,), raises=(), raise_cap=2)
    with pytest.raises(ValueError):
        SM.expected_update(S.VectorCFR(g, S.tp_keyer(5), key_ranges="current"), 0)
