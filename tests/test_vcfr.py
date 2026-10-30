"""Range-vector CFR prototype (#393): showdown kernels, tree, per-combo vs TP-keyed solver."""
import numpy as np
import pytest

from stalker.core.cards import cards
from stalker.vcfr import solver as S
from stalker.vcfr.river import REAL_BETS, REAL_RAISES, RiverGame, Showdown

BOARD = tuple(cards("Ks9h5c4d2s"))


@pytest.fixture(scope="module")
def small():
    # One bet size, no sized raise: a few decision nodes, so a few hundred iterations take about a second.
    return RiverGame(BOARD, stack=1.0, bets=(1.0,), raises=(), raise_cap=2)


def test_showdown_kernel_matches_dense_matrix():
    sd = Showdown(tuple(cards("AhKh7h3c3d")))   # paired board with a made flush: many ties and blockers
    r = np.random.default_rng(1).random(sd.n)
    wml, live = sd.dense_values(r)
    less, greater = sd.less_greater(r)
    assert np.allclose(less - greater, wml, atol=1e-9)
    assert np.allclose(sd.card_mass(r), live, atol=1e-9)
    eq = sd.equity(r)
    assert eq.min() >= 0 and eq.max() <= 1


def test_board_cards_are_removed():
    sd = Showdown(BOARD)
    assert sd.n == 1081 and not np.isin(sd.cards, BOARD).any()


def test_tree_respects_menu_and_stack():
    g = RiverGame(BOARD, stack=3.0, bets=REAL_BETS, raises=REAL_RAISES, raise_cap=3)
    most = 0.5 + g.stack
    for nd in g.nodes:
        assert max(nd.contrib) <= most + 1e-9
        if nd.kind == "act":
            assert nd.raises <= g.raise_cap
            sized = [a for a in nd.labels if a[0] in "br"]
            if nd.raises >= g.raise_cap:
                assert sized == [] and "a" not in nd.labels
    root = g.root.labels
    assert root[0] == "k" and "b300" not in root and "b20" in root and root[-1] == "a"   # 3 pots > 3.0 behind is all in


def test_zero_sum_and_best_response_bounds(small):
    rng = np.random.default_rng(2)
    strat = {nd.id: rng.dirichlet(np.ones(len(nd.children)), size=small.sd.n) for nd in small.decision_nodes()}
    assert abs(S.ev(small, strat, 0) + S.ev(small, strat, 1)) < 1e-12
    for p in (0, 1):
        assert S._value(small, strat, p, True) >= S.ev(small, strat, p) - 1e-12
    assert S.exploitability(small, strat) > 0


def test_identity_keys_equal_per_combo_solver(small):
    a, b = S.VectorCFR(small), S.VectorCFR(small, S.identity_keyer)
    a.iterate(15)
    b.iterate(15)
    sa, sb = a.materialize(), b.materialize()
    assert all(np.array_equal(sa[i], sb[i]) for i in sa)


def test_per_combo_cfr_converges(small):
    m = S.VectorCFR(small)
    m.iterate(10)
    early = S.exploitability(small, m.materialize())
    m.iterate(290)
    late = S.exploitability(small, m.materialize())
    assert late < 0.25 * early and late < 0.005     # under half a percent of the pot


def test_tp_keyed_strategy_is_constant_within_a_key(small):
    m = S.VectorCFR(small, S.tp_keyer(5))
    m.iterate(30)
    strat = m.materialize()
    root = small.root
    steps = S.quantile_steps(small.sd.equity(small.init[1]), 5)
    s = strat[root.id]
    for v in range(5):
        rows = s[steps == v]
        assert np.allclose(rows, rows[0])
    assert len(m.regret) == len(small.decision_nodes()) and all(t.shape[0] == 5 for t in m.regret.values())


def test_range_blind_key_costs_more_than_per_combo(small):
    combo = S.VectorCFR(small)
    blind = S.VectorCFR(small, S.tp_keyer(1))
    combo.iterate(200)
    blind.iterate(200)
    ref = combo.materialize()
    e_ref, e_blind = S.exploitability(small, ref), S.exploitability(small, blind.materialize())
    assert e_blind > e_ref + 0.05                       # one strategy for every hand is far from equilibrium
    assert S.head_to_head(small, blind.materialize(), ref) < 0


def test_public_tp_key_merges_nodes():
    g = RiverGame(BOARD, stack=3.0, bets=(0.5, 1.0), raises=(3.0,), raise_cap=2)
    keys = {S.public_tp_key(nd) for nd in g.decision_nodes()}
    assert len(keys) < len(g.decision_nodes())


def test_quantile_steps():
    x = np.array([0.1, 0.2, 0.2, 0.9])
    st = S.quantile_steps(x, 2)
    assert st[1] == st[2] and st[0] <= st[1] <= st[3] and st.max() <= 1


def test_tp_features_from_average_ranges_settle(small):
    # #393 finding: reading hand.equity against the current iteration's ranges (as E3 MCCFR does) keeps
    # moving the keys under the regrets; reading it against the average strategy's ranges settles.
    out = {}
    for kr in ("current", "average"):
        m = S.VectorCFR(small, S.tp_keyer(17), key_ranges=kr)
        m.iterate(300)
        out[kr] = S.exploitability(small, m.materialize())
    assert out["average"] < out["current"]


def test_key_ranges_must_be_known(small):
    with pytest.raises(ValueError):
        S.VectorCFR(small, S.tp_keyer(5), key_ranges="later")
