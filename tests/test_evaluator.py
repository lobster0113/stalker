import itertools
import random

from stalker.core.cards import COMBOS, HAND_CLASSES, cards, hand_class
from stalker.core.evaluator import (
    FLUSH, FULL_HOUSE, HIGH, PAIR, QUADS, STRAIGHT, STRAIGHT_FLUSH, TRIPS, TWO_PAIR, category, evaluate,
)


def cat(text):
    return category(evaluate(cards(text)))


def test_categories():
    assert cat("AsKsQsJsTs2d3c") == STRAIGHT_FLUSH
    assert cat("As2s3s4s5s9d9c") == STRAIGHT_FLUSH
    assert cat("AsAdAhAc2d3c4h") == QUADS
    assert cat("AsAdAhKcKd3c4h") == FULL_HOUSE
    assert cat("AsAdAhKcKdKh4h") == FULL_HOUSE
    assert cat("As9s3s4s7s9d9c") == FLUSH
    assert cat("Ad2s3c4h5s9d9c") == STRAIGHT
    assert cat("AsAdAh7c2d3c4h") == TRIPS
    assert cat("AsAdKhKc2d2c4h") == TWO_PAIR
    assert cat("AsAd9h7c2d3c4h") == PAIR
    assert cat("AsJd9h7c2d3c5h") == HIGH


def test_ordering():
    assert evaluate(cards("AsAdKhKc2d2c4h")) > evaluate(cards("AsAdKhKc3d3c2h"))  # AAKK: kicker 4 beats 3
    assert evaluate(cards("6s5d4h3c2d9c9h")) > evaluate(cards("As2d3h4c5d9c9h"))  # 6-high straight beats wheel
    assert evaluate(cards("AsKd9h7c2d")) > evaluate(cards("AsKd9h6c2d"))
    assert evaluate(cards("KsKdKhAcAd")) < evaluate(cards("AsAdAhKcKd"))


def _brute_best5(cs):
    return max(evaluate(list(c)) for c in itertools.combinations(cs, 5))


def test_seven_equals_best_five():
    rng = random.Random(7)
    for _ in range(400):
        cs = rng.sample(range(52), 7)
        assert evaluate(cs) == _brute_best5(cs)


def test_hand_classes():
    assert len(HAND_CLASSES) == 169
    assert len(COMBOS) == 1326
    assert hand_class(*cards("AsKs")) == "AKs"
    assert hand_class(*cards("2cAd")) == "A2o"
    assert hand_class(*cards("TdTh")) == "TT"
