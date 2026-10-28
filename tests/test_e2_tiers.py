import numpy as np

from referee.e2 import lbr as L
from stalker.core.cards import cards
from stalker.e2 import game as G
from stalker.e2.abstraction import BASELINE, TIERS, Abstraction, quantile_buckets
from stalker.e2.mccfr import MCCFR, infoset
from stalker.e2.tiers import table


def test_quantile_steps_hold_equal_mass_keep_order_and_share_ties():
    x = np.array([0.1, 0.2, 0.2, 0.3, 0.5, 0.9, 0.9, 0.95, 1.0, 1.0])
    b = quantile_buckets(x, np.ones(len(x)), 5)
    assert np.all(np.diff(b) >= 0) and b[1] == b[2] and b[8] == b[9]
    assert quantile_buckets(x, np.r_[0.0, np.ones(9)], 5)[0] == -1


def test_tier_buckets_split_live_combos_evenly_on_board_and_preflop():
    t = TIERS["beginner"]
    for board in ((), tuple(cards("Kc7d2s")), tuple(cards("Kc7d2sTh5c"))):
        cb = t.combo_buckets(board)
        mass = np.bincount(cb[cb >= 0], minlength=5) / (cb >= 0).sum()
        assert np.all(np.abs(mass - 0.2) < 0.05), (board, mass)
    board = tuple(cards("Kc7d2s"))
    assert t.bucket(tuple(cards("KsKd")), board) == 4 and t.bucket(tuple(cards("AsAd")), ()) == 4
    assert t.bucket(tuple(cards("7h2d")), ()) == 0


def test_baseline_abstraction_keeps_the_original_keys():
    s = G.deal(np.random.default_rng(3))
    assert infoset(s) == infoset(s, BASELINE)
    assert np.array_equal(BASELINE.combo_buckets(()), L.combo_buckets(()))
    assert Abstraction.from_json(None) == BASELINE and Abstraction.from_json(TIERS["mid"].to_json()) == TIERS["mid"]


def test_tier_policy_only_sees_its_resolution():
    m = MCCFR(2, TIERS["beginner"])
    m.iterate(40)
    assert {int(k.split("|")[2]) for k in m.policy()} <= set(range(5))


def test_lbr_reads_a_tier_policy_with_its_own_buckets():
    seen = set()

    def pol(key, acts):
        seen.add(int(key.split("|")[2]))
        return None
    L.lbr(pol, 0, 3, seed=1, abstraction=TIERS["beginner"])
    assert seen and seen <= set(range(5))


def test_tier_table_rows_are_reproducible():
    a = table([10], 2, 3, ("beginner",))
    b = table([10], 2, 3, ("beginner",))
    strip = [{k: v for k, v in r.items() if k != "train_s"} for r in a]
    assert strip == [{k: v for k, v in r.items() if k != "train_s"} for r in b]


def test_checkpoint_keeps_the_tier(tmp_path):
    from stalker.e2.abstraction import TIERS
    from stalker.e2.mccfr import MCCFR
    m = MCCFR(3, TIERS["beginner"])
    m.iterate(5)
    m.save(tmp_path / "ck.json")
    r = MCCFR.load(tmp_path / "ck.json")
    assert r.abstraction == TIERS["beginner"] and r.seed == 3
    m.iterate(5)
    r.iterate(5)
    assert m.policy() == r.policy()


def test_river_table_is_bit_identical_to_repeated_runouts():
    # #223 review: one river evaluation must not change baseline buckets through float rounding.
    from referee.anchors.hu_equity import evaluate_batch
    from stalker.e2 import abstraction as A

    board = (3, 17, 29, 40, 51)
    ok = ~np.isin(A.COMBO_ARR, list(board)).any(axis=1)
    idx = np.flatnonzero(ok)
    score = evaluate_batch(np.concatenate([A.COMBO_ARR[idx], np.broadcast_to(np.array(board), (len(idx), 5))], axis=1))
    s = np.sort(score)
    lo, hi = np.searchsorted(s, score, side="left"), np.searchsorted(s, score, side="right")
    acc = np.zeros(len(A.COMBOS))
    for _ in range(A.RUNOUTS):
        acc[idx] += (lo + (hi - lo - 1) / 2) / max(len(idx) - 1, 1)
    ref = acc / A.RUNOUTS
    ref[~ok] = np.nan
    A.ehs_table.cache_clear()
    assert np.array_equal(A.ehs_table(board), ref, equal_nan=True)
