import numpy as np
import pytest

from referee.anchors import pushfold as P
from stalker.e1 import tier_league as L
from stalker.e1 import tp_pushfold as T


@pytest.mark.parametrize("tier", ["beginner", "mid"])
def test_same_tier_field_reproduces_self_play_exactly(tier):
    r = T.train(10.0, 0.0, tier, 300, "called", "quantile")
    lg = L.train(10.0, 0.0, (tier,), {tier: 1.0}, 300)
    assert np.array_equal(r.push, lg.push[tier]) and np.array_equal(r.call, lg.call[tier])


def test_policies_are_functions_of_the_tp_value_read_against_the_field():
    lg = L.train(12.0, 0.0, L.TIERS, L.MIXES["even"], 300)
    for t in L.TIERS:
        for pol, bins in ((lg.push[t], lg.sb_bins[t]), (lg.call[t], lg.bb_bins[t])):
            assert T._is_function_of(pol, bins), t


def test_a_fine_field_turns_the_beginner_toward_the_anchor():
    # PR #289: against a pro field the beginner SB's middle bin follows Nash (fewer shoves deeper).
    def mid_bin(stack, mix_name):
        lg = L.train(stack, 0.0, L._tiers("beginner", mix_name), L.MIXES[mix_name], 600)
        b = lg.sb_bins["beginner"]
        return lg.push["beginner"][b == 2].mean()

    assert mid_bin(10.5, "pro") > mid_bin(15.0, "pro")
    assert mid_bin(10.5, "self") < mid_bin(15.0, "self")


def test_bad_mix_is_rejected():
    with pytest.raises(ValueError, match="summing to 1"):
        L.train(10.0, 0.0, L.TIERS, {"pro": 0.5}, 10)
    with pytest.raises(ValueError, match="trained tiers"):
        L.train(10.0, 0.0, ("beginner",), {"pro": 1.0}, 10)


def test_adapters_feed_the_gates():
    from referee import gate_f

    spec = L.gate_f_policy("beginner", "pro", iters=200)("sb", 10.0, 0.0)
    lg = L._league(10.0, 0.0, L.TIERS, "pro", 200, "quantile")
    assert np.array_equal(spec.probs(), lg.push["beginner"])
    assert np.array_equal(gate_f.follow(spec, 0.0), spec.probs())
    probs, bins = L.gate_s_policy("beginner", "pro", iters=200)("bb", 10.0, 0.0)
    assert probs.shape == (169,) and bins.shape == (169,)
    assert P.exploitability(10.0, 0.0, lg.push["pro"], lg.call["pro"]) < P.exploitability(10.0, 0.0, lg.push["beginner"], lg.call["beginner"])
