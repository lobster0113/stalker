import numpy as np
import pytest

from stalker.core.cards import COMBOS, cards
from stalker.core.ranges import combo_top_pct
from stalker.tp import range_shape as RS
from stalker.tp import range_shape_eval as E
from stalker.tp.reference import equity

BOARD = tuple(cards("Kc7d2s9h3c"))


def _ranges(top_mine=0.10, top_opp=0.08):
    pct = combo_top_pct()
    return (pct <= top_mine).astype(float), (pct <= top_opp).astype(float)


def test_combo_strength_equals_reference_equity():
    my_w, opp_w = _ranges()
    s = E.combo_strength(opp_w, my_w, BOARD)
    mine = [(COMBOS[j], 1.0) for j in np.flatnonzero(my_w)]
    picked = [i for i in np.flatnonzero(opp_w) if not np.isnan(s[i])][::7][:6]
    assert picked
    for i in picked:
        ref = equity(COMBOS[i], BOARD, [[(h, w) for h, w in mine if not set(h) & set(COMBOS[i])]])["equity"]
        assert s[i] == pytest.approx(ref), COMBOS[i]


def test_bins_equal_range_shape_strength_bins():
    my_w, opp_w = _ranges()
    w = opp_w * np.linspace(0.2, 1.0, len(opp_w))   # uneven weights
    fast = E.bins_from_strength(w, E.combo_strength(w, my_w, BOARD))
    mine = [(COMBOS[j], 1.0) for j in np.flatnonzero(my_w)]
    theirs = [(COMBOS[i], float(w[i])) for i in np.flatnonzero(w)]
    assert fast == pytest.approx(RS.strength_bins(theirs, mine, BOARD))


def test_combo_strength_rejects_turn():
    my_w, opp_w = _ranges()
    with pytest.raises(ValueError, match="river"):
        E.combo_strength(opp_w, my_w, BOARD[:4])


def test_quantize_keeps_a_distribution_on_the_step_grid():
    rng = np.random.default_rng(1)
    for _ in range(100):
        b = rng.dirichlet(np.ones(5))
        q = E.quantize(b)
        assert q.sum() == pytest.approx(1.0)
        assert np.allclose(q * 20, np.round(q * 20))
        assert np.abs(q - b).max() <= 0.05 + 1e-9
    n = E.noisy(b, rng)
    assert n.sum() == pytest.approx(1.0) and (n >= 0).all()


def test_unknown_archetype_is_rejected():
    with pytest.raises(ValueError, match="archetype"):
        E.archetype_range("capped", np.ones(3), np.array([0.1, 0.5, 0.9]), np.random.default_rng(0))


def test_archetypes_mostly_produce_their_shape():
    spots = E.run(10, seed=7)
    for a in E.ARCHETYPES:
        own = [s for s in spots if s.archetype == a]
        assert sum(s.shape == a for s in own) >= 6, a


def test_discrimination_matches_the_research_note():
    # docs/research/2026-10-28-range-shape.md: right shape beats the linear template by more than the
    # input loss; condensed beats even the best width answer; on linear spots there is nothing to gain.
    summ = E.summarize(E.run(30, seed=159))
    for shape in ("polar", "condensed"):
        assert summ[shape]["gap_vs_linear_template"] > summ[shape]["input_loss_noisy"], shape
    assert summ["condensed"]["gap_vs_best_width"] > summ["condensed"]["input_loss_noisy"]
    assert summ["linear"]["gap_vs_linear_template"] == 0
