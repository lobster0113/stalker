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


def test_rule_head_threshold_is_the_pot_odds():
    dc = dataclasses.replace(_facing_bet_dc(), required_equity=0.38)
    tp = TPVector({"hand.equity": 45.0, "board.adv": 70.0}, load())
    attrs = A.attribute(PotOddsHead(), tp, dc)
    top = attrs[0]
    assert top.item == "hand.equity" and top.contribution == pytest.approx(1.0)
    assert top.threshold == pytest.approx(37.0) and top.flips_to == "fold" and top.below
    # An item the head does not read gets zero and no threshold.
    adv = next(a for a in attrs if a.item == "board.adv")
    assert adv.contribution == 0 and adv.threshold is None


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
