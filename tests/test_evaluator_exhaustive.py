"""Exhaustive / cross-implementation checks of the three hand evaluators.

An evaluator bug silently poisons every downstream number, so the 5-card space is enumerated
in full and 7-card hands are compared against "best of the 21 five-card subsets".
"""
import itertools
from collections import Counter

import numpy as np
import pytest

from referee.anchors.hu_equity import evaluate_batch
from referee.gate_r.evaluator import strength
from stalker.core.cards import card_str
from stalker.core.evaluator import category, evaluate

CATEGORY_COUNTS = {
    8: 40, 7: 624, 6: 3744, 5: 5108, 4: 10200, 3: 54912, 2: 123552, 1: 1098240, 0: 1302540,
}
CATEGORY_CLASSES = {8: 10, 7: 156, 6: 156, 5: 1277, 4: 10, 3: 858, 2: 858, 1: 2860, 0: 1277}


def _ref_key(cs):
    s = [card_str(c) for c in cs]
    return strength(s[:2], s[2:])


def _sample7(n, seed):
    rng = np.random.default_rng(seed)
    out = np.empty((n, 7), dtype=np.int64)
    for i in range(n):
        out[i] = rng.choice(52, size=7, replace=False)
    return out


def _best_of_21(hand):
    return max(evaluate(list(c)) for c in itertools.combinations(hand, 5))


def _check_7card(n, seed, ref_n):
    hands = _sample7(n, seed)
    batch = evaluate_batch(hands)
    for i, h in enumerate(hands.tolist()):
        want = _best_of_21(h)
        assert evaluate(h) == want, f"core evaluate != best of 21 for {h}; fix stalker/core/evaluator.py"
        assert batch[i] == want, f"evaluate_batch != core for {h}; fix referee/anchors/hu_equity.py"
    # Referee evaluator: order-isomorphic to core on pairs of hands (equal <=> equal, < <=> <).
    scores = [evaluate(h) for h in hands[:ref_n].tolist()]
    keys = [_ref_key(h) for h in hands[:ref_n].tolist()]
    for i in range(ref_n - 1):
        a, b = (scores[i] > scores[i + 1]) - (scores[i] < scores[i + 1]), \
               (keys[i] > keys[i + 1]) - (keys[i] < keys[i + 1])
        assert a == b, f"referee strength order differs from core at {hands[i].tolist()}"
    for s, k in zip(scores, keys):
        assert category(s) == k[0], "referee category differs from core"


def test_seven_card_vs_best_of_21_small():
    _check_7card(10_000, seed=121, ref_n=2_000)


@pytest.mark.slow
def test_seven_card_vs_best_of_21_million():
    _check_7card(1_000_000, seed=1210, ref_n=100_000)


@pytest.mark.slow
def test_five_card_exhaustive():
    counts = Counter()
    scores = set()
    rep = {}
    for c in itertools.combinations(range(52), 5):
        s = evaluate(c)
        scores.add(s)
        counts[category(s)] += 1
        rep.setdefault(s, c)
    assert len(scores) == 7462, f"{len(scores)} distinct ranks, want 7462"
    assert dict(counts) == CATEGORY_COUNTS
    per_cat = Counter(category(s) for s in scores)
    assert dict(per_cat) == CATEGORY_CLASSES
    # Referee evaluator induces the same ranking on the 7462 representatives.
    ordered = sorted(scores)
    keys = [_ref_key(rep[s]) for s in ordered]
    assert all(a < b for a, b in zip(keys, keys[1:])), "referee strength not order-isomorphic to core"
