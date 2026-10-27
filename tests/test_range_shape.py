import numpy as np
import pytest

from stalker.core.cards import cards
from stalker.tp import range_shape as RS
from stalker.tp.reference import parse_range

BOARD = tuple(cards("Kc7d2s9h3c"))  # river
MINE = parse_range([["AhAd", 1], ["8h8d", 1]])


def _bins(rng):
    return RS.strength_bins(parse_range(rng), MINE, BOARD)


def test_polar_range_hand_calculated():
    # KK = set (beats AA and 88: 100%) -> 넛급; 54 and 65 lose to both (0%) -> 에어.
    b = _bins([["KsKd", 1], ["5h4h", 1], ["6h5c", 1]])
    assert b == pytest.approx([2 / 3, 0, 0, 0, 1 / 3])
    assert RS.shape_of(b) == "polar"


def test_condensed_and_capped_range_hand_calculated():
    # QQ, JJ beat 88 and lose to AA; AK (top pair) the same: all exactly 50% -> 중간 [50,75).
    b = _bins([["QsQd", 1], ["JhJs", 1], ["AsKs", 1]])
    assert b == pytest.approx([0, 0, 1, 0, 0])
    assert RS.shape_of(b) == "condensed"
    # My AA beats all three (100%) and 88 loses to all (0%): my 넛급 mass 1/2, theirs 0 -> capped.
    mine_vs_them = RS.strength_bins(MINE, parse_range([["QsQd", 1], ["JhJs", 1], ["AsKs", 1]]), BOARD)
    assert mine_vs_them[4] == pytest.approx(0.5) and RS.capped(b, mine_vs_them)


def test_linear_range():
    b = _bins([["KsKd", 2], ["QsQd", 1]])
    assert b == pytest.approx([0, 0, 1 / 3, 0, 2 / 3])
    assert RS.shape_of(b) == "linear"


def test_same_width_different_shape_gets_a_different_score():
    # The point of #159: a polar range read as "linear, same width" must lose points.
    truth = _bins([["KsKd", 1], ["5h4h", 1], ["6h5c", 1]])
    assert RS.score(truth, truth) == 100
    # Reading a polar range as linear loses points (hand calc: polar template 82, linear template 63).
    assert RS.score(RS.TEMPLATES["polar"], truth) == 82 and RS.score(RS.TEMPLATES["linear"], truth) == 63
    assert RS.score([0, 0, 1, 0, 0], truth) == 50  # hand calc: cumulative gaps .667+.667+.333+.333 = 2.0 / 4


def test_emd_bounds_and_validation():
    assert RS.emd([1, 0, 0, 0, 0], [0, 0, 0, 0, 1]) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="sum to 1"):
        RS.emd([0.5, 0, 0, 0, 0], [0, 0, 0, 0, 1])
    with pytest.raises(ValueError, match="turn and river"):
        RS.strength_bins(parse_range([["KsKd", 1]]), MINE, BOARD[:3])


def test_templates_are_distributions_with_their_own_shape():
    for name, t in RS.TEMPLATES.items():
        assert sum(t) == pytest.approx(1.0)
        assert RS.shape_of(t) == name, name


def test_emd_is_a_metric_on_random_distributions():
    rng = np.random.default_rng(159)
    for _ in range(200):
        a, b, c = (rng.dirichlet(np.ones(5)) for _ in range(3))
        assert RS.emd(a, b) == pytest.approx(RS.emd(b, a))
        assert RS.emd(a, c) <= RS.emd(a, b) + RS.emd(b, c) + 1e-12
        assert RS.emd(a, a) == pytest.approx(0.0)


def test_every_template_scores_100_against_itself():
    for t in RS.TEMPLATES.values():
        assert RS.score(t, t) == 100


def test_width_default_is_linear_and_tighter_means_stronger():
    tight, mid, loose = RS.width_default(0.05), RS.width_default(0.30), RS.width_default(0.80)
    for d in (tight, mid, loose):
        assert sum(d) == pytest.approx(1.0)
    assert tight[4] > mid[4] > loose[4] and tight[0] < mid[0] < loose[0]
    assert RS.shape_of(tight) == "linear"
    with pytest.raises(ValueError, match="width"):
        RS.width_default(0)
