import pytest

from referee.gate_t import REGISTRY, t3
from stalker.tp.bottleneck import default_agent


class _Fake:
    """Wraps the registered agent and edits its TP values: T3 must catch each planted defect."""

    def __init__(self, edit):
        self.base, self.edit = default_agent(), edit

    def tp(self, po, tier="pro"):
        return self.edit(dict(self.base.tp(po)), po)


def _set(item, value):
    return lambda v, po: {**v, item: value}


def test_t3_passes_for_registered_agents():
    for make in REGISTRY.values():
        passed, total, fails = t3.check_t3(make())
        assert passed == total > 100 and not fails


@pytest.mark.parametrize("name,edit", [
    ("above scale", _set("hand.equity", 101.0)),
    ("fraction", _set("hand.equity", 37.5)),
    ("negative", _set("hand.equity", -1.0)),
    ("range with wrong cell count", _set("opp.range", (50.0,) * 168)),
    ("range cell fraction", _set("opp.range", (0.5,) * 169)),
    ("N/A value (board.adv preflop)", lambda v, po: {**v, "board.adv": 50.0} if not po.board else v),
    ("N/A value (outs on river or preflop)", lambda v, po: {**v, "hand.outs": 10.0} if len(po.board) in (0, 5) else v),
    ("item not asked at beginner tier", _set("board.nut", 50.0)),
    ("unknown item", _set("made.up", 50.0)),
])
def test_t3_catches_planted_defects(name, edit):
    passed, total, fails = t3.check_t3(_Fake(edit))
    assert passed < total and fails, name


def test_t3_failure_message_names_item_and_fix():
    _, _, fails = t3.check_t3(_Fake(_set("hand.equity", 101.0)))
    assert "hand.equity" in fails[0] and "Fix the TP head" in fails[0]


def test_t3_allows_missing_values_and_risk_premium_range():
    spec = t3.load()
    po = t3._observations()[0]
    assert t3.decision_errors(spec, {"hand.equity": None}, "pro", po) == []
    assert t3._scale_error("risk_premium_pp", -12.5) is None
    assert t3._scale_error("risk_premium_pp", 101) is not None
    assert t3._scale_error("0-100", float("nan")) is not None
