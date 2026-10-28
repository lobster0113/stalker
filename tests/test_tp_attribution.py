import dataclasses

import pytest

from referee import gate_t
from stalker.env.contract import decision_context
from stalker.tp import attribution as A
from stalker.tp.bottleneck import TPVector, default_agent
from stalker.tp.spec import load


class PotOddsHead:
    """Hand-made rule: call when equity (%) >= required equity (%), else fold. Reads nothing else."""

    def act(self, tp, dc):
        eq = tp["hand.equity"] or 0.0
        return {"call": 1.0, "fold": 0.0} if eq >= 100 * dc.required_equity else {"call": 0.0, "fold": 1.0}


def _facing_bet_dc():
    po = next(p for p in gate_t._observations() if decision_context(p).to_call > 0)
    return decision_context(po)


@pytest.mark.parametrize("tier,contribution,threshold", [("pro", 0.0, 37.0), ("mid", 1.0, 30.0), ("beginner", 1.0, 25.0)])
def test_rule_head_threshold_follows_the_tier_grid(tier, contribution, threshold):
    # #249 review: one step and the threshold come from the tier's answer grid (pro 1, mid 10,
    # beginner 25): 45 -> 44 does not cross the 38% price, 45 -> 35 or 20 does; a beginner cannot
    # answer 37, so the nearest answerable flip is 25.
    dc = dataclasses.replace(_facing_bet_dc(), required_equity=0.38)
    tp = TPVector({"hand.equity": 45.0, "board.adv": 70.0}, load())
    attrs = A.attribute(PotOddsHead(), tp, dc, tier=tier)
    eq = next(a for a in attrs if a.item == "hand.equity")
    assert eq.contribution == pytest.approx(contribution)
    assert eq.threshold == pytest.approx(threshold) and eq.flips_to == "fold" and eq.below
    # An item the head does not read gets zero and no threshold.
    adv = next(a for a in attrs if a.item == "board.adv")
    assert adv.contribution == 0 and adv.threshold is None


def test_beginner_step_is_25():
    assert A.tier_step(load(), "beginner") == 25 and A.tier_step(load(), "mid") == 10 and A.tier_step(load(), "pro") == 1
    assert A.answer_grid(load(), "beginner", "hand.equity") == [0, 25, 50, 75, 100]
    assert A.answer_grid(load(), "mid", "plan.icm")[:3] == [-100, -90, -80]


def test_explain_sentences():
    dc = dataclasses.replace(_facing_bet_dc(), required_equity=0.38)
    tp = TPVector({"hand.equity": 45.0}, load())
    lines = A.explain(A.attribute(PotOddsHead(), tp, dc), {"hand.equity": "에퀴티 감각"})
    assert lines == ["에퀴티 감각: 37 이하이면 fold"]


def test_na_items_are_not_explained_and_registered_agent_works():
    agent = default_agent()
    po = gate_t._observations()[0]
    tp = TPVector({"hand.equity": 60.0}, agent.spec)
    attrs = A.attribute(agent.action_head, tp, decision_context(po))
    assert [a.item for a in attrs] == ["hand.equity"]
    assert 0 <= attrs[0].contribution <= 1


def test_tv_distance():
    assert A.tv({"a": 1.0}, {"b": 1.0}) == 1.0
    assert A.tv({"a": .5, "b": .5}, {"a": .5, "b": .5}) == 0.0


class IcmHead:
    """Fold when the ICM risk premium (pp) exceeds 5, else call; reads plan.icm only."""

    def act(self, tp, dc):
        return {"call": 0.0, "fold": 1.0} if (tp["plan.icm"] or 0.0) > 5 else {"call": 1.0, "fold": 0.0}


def test_range_items_are_skipped_and_premium_scale_is_respected():
    # opp.range holds 169 cells (no single step to move); plan.icm lives in -100..100 pp.
    dc = _facing_bet_dc()
    tp = TPVector({"opp.range": [40.0] * 169, "plan.icm": -2.0}, load())
    attrs = A.attribute(IcmHead(), tp, dc)
    assert {a.item for a in attrs} == {"plan.icm"}
    (icm,) = attrs
    assert icm.threshold == pytest.approx(6.0) and icm.flips_to == "fold" and not icm.below
