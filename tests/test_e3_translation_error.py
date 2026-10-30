"""High-translation-error rule (#417) and the translation reliability sweep."""
import numpy as np
import pytest

from stalker.e3 import game as G
from stalker.e3 import translate as X
from stalker.tools import translation_map as M


def _deal(menu="v1", cap=G.RAISE_CAP, stack_bb=None):
    s = G.deal(np.random.default_rng(1), 6, menu, cap)
    if stack_bb is not None:
        s = s._replace(stack=tuple(stack_bb * G.BB - b for b in s.bet))
    return s


def _play(s, *acts):
    for a in acts:
        s = G.apply(s, a)
    return s


def test_v1_open_split_with_all_in_is_flagged_unless_near_all_in():
    s = _deal()
    assert [a for a, _ in X.split(s, 400)] == ["r", "a"]
    assert X.high_translation_error(s, 400)          # the issue's 4BB open: 2.5BB or all in
    assert X.high_translation_error(s, 260)          # any weight on an all-in reading of a non-all-in size
    assert not X.high_translation_error(s, 250)      # exact menu size
    assert not X.high_translation_error(s, 220)      # below the smallest size: one label
    assert not X.high_translation_error(s, 10000)    # all in
    edge = int(G.ALLIN_MERGE * 10000)
    assert X.high_translation_error(s, edge - 10) and not X.high_translation_error(s, edge)


def test_short_stack_exemption_scales_with_the_stack():
    s = _play(_deal(stack_bb=15), "f", "f", "f")
    assert X.high_translation_error(s, 1190) and not X.high_translation_error(s, 1200)


def test_gap_rule_flags_v1_flop_b33_b75_only_far_from_both():
    s = _play(_deal(), "f", "f", "f", "r", "f", "c")
    assert s.street == 1 and dict(X._menu(s))["b33"] == 182 and dict(X._menu(s))["b75"] == 412
    mids = [to for to in range(190, 410, 10) if X.F_BAND[0] < X.split(s, to)[0][1] < X.F_BAND[1]]
    assert mids and all(X.high_translation_error(s, to) for to in mids)
    near = [to for to in range(190, 410, 10) if to not in mids]
    assert near and not any(X.high_translation_error(s, to) for to in near)


def test_real_menu_neighbours_are_close_enough_for_the_gap_rule():
    # Real sizes are at most 1.65x apart as pot fractions, so only the all-in edge flags (#417 calibration).
    s = _deal("real", None)
    assert not any(X.high_translation_error(s, to) for to in range(200, 1001, 10))
    assert X.high_translation_error(s, 1100)         # between r10 and all in
    f = _play(_deal("real", None), "f", "f", "f", "r", "f", "c")
    top = max(t for a, t in X._menu(f) if a != "a")
    assert not any(X.high_translation_error(f, to) for to in range(f.bet[f.to_act] + G.BB, top + 1, 10))


def test_capped_street_maps_to_all_in_and_is_never_flagged():
    s = _play(_deal(), "f", "f", "r", "r", "f", "f", "r")   # BTN faces a 4-bet: the 5-bet is all in only
    assert all(X.split(s, to) == [("a", 1.0)] for to in (3000, 6000, 9000))
    assert not any(X.high_translation_error(s, to) for to in (3000, 6000, 9000))


def test_rule_raises_like_split_on_an_illegal_amount():
    s = _deal()
    with pytest.raises(ValueError, match="below the min raise"):
        X.high_translation_error(s, 150)


def test_sweep_reports_split_legality_tv_and_flags():
    m = M.Mapper({}, 5, "basic", "v1", G.RAISE_CAP)   # empty table: uniform rows, still exercises every step
    sp = m.spot("open UTG", [])
    out = M.grid(m, sp, 200, 500)[0]
    assert out["legal_mask"] == {"r": True, "a": True} and out["least"] == 200 and out["room"] == 10000
    rows = {r["to"]: r for r in out["grid"]}
    assert rows[200]["min_raise"] and rows[200]["split"] == [["r", 1.0]] and not rows[200]["flag"]
    assert rows[400]["flag"] and 0.0 <= rows[400]["tv"] <= rows[400]["tv_hand"] <= 1.0
    assert set(out["pairs"]) == {"r|a"} and rows[10000]["all_in"]
    summ = M.summarize(out)
    assert summ["flag_bb"] == [[2.6, 5.0]] and summ["split"] == summ["flagged"]


def test_sweep_spots_cover_the_issue_grid():
    m = M.Mapper({}, 5, "basic", "v1", G.RAISE_CAP)
    names = [sp.name for sp, _, _ in M.spots(m)]
    for part in ("open UTG", "open SB", "3bet", "4bet", "5bet", "all-in edge", "15BB", "flop bet", "flop raise"):
        assert any(part in n for n in names), part
