import numpy as np

from referee.e3 import lbr as L
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR


def folder(key, acts):
    return [1.0 if a == "f" else 0.0 for a in acts] if "f" in acts else None


def test_lbr_crushes_a_policy_that_folds_to_any_bet():
    r = L.lbr(folder, seat=0, hands=30, seed=1)
    # UTG raises every hand and collects the blinds (1.5bb) at least.
    assert r.mean_bb >= 1.4


def test_lbr_is_reproducible_and_reports_every_seat():
    a = L.exploitability_lb({}, 3, seed=2, seats=[0, 5])
    assert a == L.exploitability_lb({}, 3, seed=2, seats=[0, 5])
    assert set(a["by_seat"]) == {"UTG", "BB"}


def test_lbr_reads_the_policy_with_the_training_keys():
    m = E3MCCFR(3, 5)
    m.iterate(2)
    seen = []

    def spy(key, acts):
        seen.append(key)
        return m.policy().get(key)
    L.lbr(spy, seat=2, hands=2, seed=4)
    assert seen and all(k.split("|")[-1].startswith("e") for k in seen)  # TP keys end in the equity step
    assert any(k in m.policy() for k in seen) or not m.policy()


def test_seat_probs_zero_board_collisions():
    s = G.deal(np.random.default_rng(5))
    for a in ("c", "f", "f", "f", "f", "c"):
        s = G.apply(s, a)
    pr = L.seat_probs({}, s, s.to_act, K.initial_ranges(6), 5)
    from stalker.e2.eq_view import COMBO_ARR
    dead = np.isin(COMBO_ARR, list(s.board)).any(axis=1)
    assert np.all(pr[dead] == 0) and np.allclose(pr[~dead].sum(axis=1), 1)
