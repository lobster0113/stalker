import hashlib
import json
from pathlib import Path

import numpy as np

from stalker import train_jobs as T
from stalker.e2.eq_view import N
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR


def _play(s, *acts):
    for a in acts:
        s = G.apply(s, a)
    return s


def _hu_flop(seed=0):
    # UTG raises, everyone folds to the big blind, who calls: UTG (0) vs BB (5) on the flop.
    s = _play(G.deal(np.random.default_rng(seed)), "r", "f", "f", "f", "f", "c")
    assert s.street == 1 and s.live() == [0, 5]
    return s


def test_beginner_and_mid_keys_are_unchanged_by_the_pro_tier():
    # Key strings and visit counts of a short run, pinned before #325 (strings, not floats, so the
    # pin holds with and without numba).
    pins = {"beginner": "468a9b09738234319cb2f98c177938ce88bed098ac3afa433a84319771dea4dd",
            "mid": "635096391460e7afdce58b18ee12199fabf027aff2ea53bf7edbfcb17e0e3304"}
    for tier, pin in pins.items():
        m = E3MCCFR(11, K.TIER_K[tier], 6, K.TIER_DEPTH[tier])
        m.iterate(3)
        assert hashlib.sha256(json.dumps(sorted(m.visits.items())).encode()).hexdigest() == pin, tier


def test_board_nut_is_heads_up_postflop_only_and_follows_the_ranges():
    s = _hu_flop()
    r = K.initial_ranges(6)
    assert abs(K.board_nut(s, 0, r) - 50.0) < 1e-9  # same range both sides
    assert K.board_nut(G.deal(np.random.default_rng(0)), 0, r) is None  # preflop
    multi = _play(G.deal(np.random.default_rng(0)), "r", "f", "f", "f", "c", "c")
    assert len(multi.live()) == 3 and K.board_nut(multi, 0, K.initial_ranges(6)) is None
    strength = K._equity_cached(tuple(s.board), K._UNIFORM)
    strong = np.nan_to_num(strength) >= np.nanquantile(strength, 0.9)
    me_strong = list(r)
    me_strong[0] = strong.astype(float)          # my public range: only near-nut combos
    assert K.board_nut(s, 0, me_strong) < 20 and K.board_nut(s, 5, me_strong) > 80


def test_scale_and_foldy_steps():
    assert [K.scale_step(v, 17) for v in (0, 5.8, 6.0, 50, 100)] == [0, 0, 1, 8, 16]   # 100/17 = 5.88-point bins
    assert K.foldy_step() == "N" and K.foldy_step(5, 5) == "N"   # N/A below 6 faced bets
    assert K.foldy_step(6, 6) == str(K.scale_step(100 * 9 / 12, 17))   # shrunk toward 50%
    assert K.foldy_step(0, 1000) == "0" and K.foldy_step(1000, 1000) == "16"


def test_board_nut_uses_the_coarse_table_grid():
    # #332: 5 board.nut steps in the table, not the 17 used for hand.equity
    assert K.NUT_K == 5
    vals = {K.scale_step(v, K.NUT_K) for v in range(0, 101)}
    assert vals == set(range(K.NUT_K))
    assert K.theoretical_keys(6, K.K_PRO, "pro") < K.theoretical_keys(6, K.K_PRO, "full") * (2 + 17) / 3


def test_grading_scale_for_board_nut_is_unchanged_by_the_table_grid():
    # #332 review: NUT_K is the table's abstraction only; a person's board.nut answer is still graded on
    # the TP spec's 0-100 scale within the pro tolerance (TP.md §4.1), and tp_key does not read the spec.
    from stalker.tp.spec import load

    spec = load()
    assert spec.item("board.nut")["scale"] == "0-100" and "board.nut" in spec.tier_items("pro")
    assert spec.data["tiers"]["pro"]["tolerance"] == 3
    assert K.NUT_K < K.K_PRO and "tp.spec" not in Path(K.__file__).read_text(encoding="utf-8")


def test_pro_key_extends_full_and_encodes_nut_with_the_equity_step():
    s = _hu_flop()
    r = K.initial_ranges(6)
    assert K.public_key(s, 0, "pro") == f"p|{K.public_key(s, 0, 'full')}|fN"
    mid = K.equity_steps(s, 0, r, K.TIER_K["mid"])
    assert mid.max() < K.TIER_K["mid"]                    # other tiers carry no nut step
    pro = K.equity_steps(s, 0, r, K.K_PRO)
    live = pro >= 0
    assert (pro[live] >= K.NUT_BASE).all() and (pro[live] % K.NUT_BASE < K.K_PRO).all()
    nut = K.nut_step(s, 0, r)
    assert (pro[live] // K.NUT_BASE - 1 == nut).all()
    v = int(pro[live][0])
    assert K.key("x", v) == f"x|e{v % K.NUT_BASE}|n{nut}" and K.key("x", 3) == "x|e3"
    pre = K.equity_steps(G.deal(np.random.default_rng(1)), 0, K.initial_ranges(6), K.K_PRO)
    assert pre.max() < K.K_PRO                            # preflop: no nut step
    assert len(pro) == N


def test_pro_tier_trains_within_its_key_bound():
    m = E3MCCFR(4, K.TIER_K["pro"], 6, K.TIER_DEPTH["pro"])
    m.iterate(6)
    assert 0 < len(m.regret) <= K.theoretical_keys(6, m.k, m.depth)
    assert all(k.startswith(("p|", "call|")) for k in m.regret)
    assert K.theoretical_keys(6, 17, "pro") > K.theoretical_keys(6, 17, "full")
    assert m.policy() and all(abs(sum(p) - 1) < 1e-9 for p in m.policy().values())


def test_pro_job_is_registered_and_resumable():
    assert "e3-tp-pro-w4" in T.JOBS and "e3-tp-pro-w4" in T.RESUMABLE
    kw = T.JOBS["e3-tp-pro-w4"].keywords
    assert kw["tier"] == "pro" and kw["workers"] == 4
