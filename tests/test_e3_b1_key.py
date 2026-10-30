"""Key variant b1 (#398): suit-aware hand.outs / hand.vuln / hand.block in the TP key."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from stalker import train_jobs as T
from stalker.core.cards import cards, combo_index
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR


def _state(board_text, live=(0, 5)):
    b = cards(board_text)
    return SimpleNamespace(street=len(b) - 2, board=b, live=lambda: list(live))


def _code(s, hand, depth="full"):
    return int(K.b1_code(s, 0, K.initial_ranges(6), depth)[combo_index(*cards(hand))])


def test_nut_flush_draw_and_weak_made_hand_get_different_keys_at_the_same_equity():
    s = _state("Ks7s2d")
    ov = K.hand_outs_vuln(s, 0, K.initial_ranges(6))
    idx = {h: combo_index(*cards(h)) for h in ("As4s", "Kd3c")}
    outs, vuln = ov
    assert outs[idx["As4s"]] > 20 > outs[idx["Kd3c"]]      # the spade cards (and an ace) help the draw
    steps = K.equity_steps(s, 0, K.initial_ranges(6), 11, "")
    draw, made = "As4s", "7c4c"                              # top pair-less nut draw vs a weak made pair
    assert steps[combo_index(*cards(draw))] == steps[combo_index(*cards(made))]
    assert _code(s, draw) != _code(s, made)
    assert K.b1_label(_code(s, draw)) != K.b1_label(_code(s, made))
    b1 = K.equity_steps(s, 0, K.initial_ranges(6), 11, "b1", "full")
    assert b1[combo_index(*cards(draw))] != b1[combo_index(*cards(made))]


def test_outs_count_the_suit_of_the_draw_not_just_the_rank():
    s = _state("Ks7s2d")
    outs, _ = K.hand_outs_vuln(s, 0, K.initial_ranges(6))
    flush_draw, offsuit = (outs[combo_index(*cards(h))] for h in ("Qs9s", "Qh9d"))
    assert flush_draw > offsuit + 10


def test_river_has_no_outs_or_vuln_but_still_a_block_bucket():
    s = _state("Ks7s2d9c3h")
    assert K.hand_outs_vuln(s, 0, K.initial_ranges(6)) is None
    label = K.b1_label(_code(s, "As4c"))
    assert label.startswith("o-v-k") and label[-1] != "-"


def test_spade_blocker_changes_the_key_in_the_deep_tier_only_for_a_blocker():
    s = _state("Ks7s9s")
    blocker, plain = _code(s, "As3c"), _code(s, "Ad3c")
    assert blocker != plain
    k_block = K.b1_label(blocker).split("k")[1]
    k_plain = K.b1_label(plain).split("k")[1]
    assert int(k_block) > int(k_plain)


def test_spade_blocker_changes_the_key_in_the_pro_tier_at_the_same_equity():
    s = _state("Ks7s9s")
    steps = K.equity_steps(s, 0, K.initial_ranges(6), K.K_PRO, "")
    blocker, plain = "As3c", "2s2h"
    assert steps[combo_index(*cards(blocker))] % K.NUT_BASE == steps[combo_index(*cards(plain))] % K.NUT_BASE
    b1 = K.equity_steps(s, 0, K.initial_ranges(6), K.K_PRO, "b1")
    assert b1[combo_index(*cards(blocker))] != b1[combo_index(*cards(plain))]


def test_tiers_ask_only_their_own_items():
    s = _state("Ks7s9s")
    assert K.b1_label(_code(s, "As3c", "basic")) .count("v") == 0 and "k" not in K.b1_label(_code(s, "As3c", "basic"))
    assert set(K.b1_label(_code(s, "As3c", "full"))) >= set("ovk")


def test_key_string_carries_the_label_but_preflop_and_call_keys_do_not():
    s = _state("Ks7s9s")
    step = 3 + K.B1_BASE * (1 + _code(s, "As3c"))
    assert K.key("pub", step) == f"pub|e3|{K.b1_label(_code(s, 'As3c'))}"
    assert K.key("call|1|1|2", step) == "call|1|1|2|e3"
    assert K.key("pub", 3) == "pub|e3"
    pre = G.deal(np.random.default_rng(0))
    plain = K.equity_steps(pre, pre.to_act, K.initial_ranges(6), 11)
    assert np.array_equal(plain, K.equity_steps(pre, pre.to_act, K.initial_ranges(6), 11, "b1", "full"))


def test_plain_variant_is_unchanged_and_pro_nut_encoding_still_decodes():
    s = G.deal(np.random.default_rng(1))
    r = K.initial_ranges(6)
    assert np.array_equal(K.equity_steps(s, s.to_act, r, 11), K.equity_steps(s, s.to_act, r, 11, ""))
    assert K.key("p|x", 4 + K.NUT_BASE * 3) == "p|x|e4|n2"
    assert K.key("p|x", 4 + K.NUT_BASE * 3 + K.B1_BASE * (1 + 7)) == f"p|x|e4|n2|{K.b1_label(7)}"


@pytest.mark.slow   # b1 costs ~16x per iteration (next-card equities), so even 10 hands take a while
def test_b1_training_is_reproducible_and_keys_differ_from_plain():
    a, b, plain = (E3MCCFR(3, 5, 3, "basic", key_variant=v) for v in ("b1", "b1", ""))
    for m in (a, b, plain):
        m.iterate(10)
    assert a.policy() == b.policy()
    assert any("|o" in k for k in a.regret) and not any("|o" in k for k in plain.regret)
    assert len(a.regret) <= K.theoretical_keys(3, a.k, a.depth, "b1")
    assert K.theoretical_keys(6, 11, "full", "b1") > K.theoretical_keys(6, 11, "full")


def test_checkpoint_keeps_the_variant_and_refuses_older_code_via_version():
    m = E3MCCFR(1, 5, 3, "basic", key_variant="b1")
    m.iterate(2)
    st = json.loads(json.dumps(m.state()))
    assert st["version"] == 4 and st["key_variant"] == "b1"
    assert E3MCCFR.from_state(st).key_variant == "b1"
    assert E3MCCFR(1, 5, 3, "basic").state()["version"] == 1
    with pytest.raises(ValueError, match="key_variant"):
        E3MCCFR(0, 5, 3, "basic", key_variant="b2")


@pytest.mark.slow
def test_parallel_workers_train_with_the_variant():
    from stalker.e3 import parallel
    m = E3MCCFR(2, 5, 3, "basic", key_variant="b1")
    parallel.iterate(m, 8, workers=2, batch=4)
    assert any("|o" in k for k in m.regret)


def test_b1_job_is_registered_resumable_and_refuses_a_plain_checkpoint(tmp_path):
    job = "e3-tp-mid-b1-w4"
    assert job in T.JOBS and job in T.RESUMABLE
    kw = T.JOBS[job].keywords
    assert (kw["tier"], kw["workers"], kw["key_variant"]) == ("mid", 4, "b1")
    assert T.JOBS["e3-tp-mid-w4"].keywords.get("key_variant", "") == ""
    m = E3MCCFR(1, 11, 6, "full")
    (tmp_path / f"{job}-seed1.ckpt.json").write_text(json.dumps(m.state()), encoding="utf-8")
    with pytest.raises(SystemExit, match="key variant"):
        T.JOBS[job](1, 1, tmp_path / "out", resume=tmp_path)


def test_b1_and_own_average_rule_checkpoint_round_trips_as_version_4():
    m = E3MCCFR(1, 5, 3, "basic", avg_rule="own", key_variant="b1")
    m.iterate(1)
    st = json.loads(json.dumps(m.state()))
    r = E3MCCFR.from_state(st, "own")
    assert (st["version"], r.avg_rule, r.key_variant) == (4, "own", "b1")
    with pytest.raises(ValueError, match="avg_rule"):
        E3MCCFR.from_state(st, "legacy")
