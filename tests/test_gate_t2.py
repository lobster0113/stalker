import time

import numpy as np
import pytest

from referee import gate_t
from referee.anchors import hu_equity
from referee.gate_t import t2
from stalker.core.cards import HAND_CLASSES, card, hand_class
from stalker.core.ranges import class_equity
from stalker.tp.bottleneck import BottleneckAgent, TPVector, default_agent, public_head


def _agent(edit):
    """The registered agent with its TP head output edited by `edit(values, po)`."""
    base = default_agent()
    head = public_head(base.spec)

    def tp(po):
        vals = {k: v for k, v in head(po).items() if v is not None}
        edit(vals, po)
        return TPVector(vals, base.spec)
    return BottleneckAgent(tp, base.action_head, base.spec)


@pytest.fixture(scope="module")
def decisions():
    return gate_t._decisions_with(default_agent(), ["hand.equity"], t2.T2_DECISIONS)


def test_registered_agent_passes_and_runs_within_the_quick_budget():
    t0 = time.monotonic()
    passed, total, fails = t2.check_t2(default_agent())
    assert time.monotonic() - t0 < 10, "T2 must add at most 10s to gates quick; lower T2_DECISIONS"
    assert total == t2.T2_DECISIONS and passed == total, fails


def test_decisions_cover_heads_up_and_multiway(decisions):
    counts = {t2._opponents(po) for po in decisions}
    assert 1 in counts and any(n > 1 for n in counts)


def test_equity_against_one_random_hand_in_a_multiway_pot_fails(decisions):
    def heads_up_only(vals, po):
        a, b = (card(c) for c in po.hole_cards)
        vals["hand.equity"] = 100.0 * class_equity(hand_class(a, b), 1)

    passed, total, fails = t2.check_t2(_agent(heads_up_only), decisions)
    multiway = sum(t2._opponents(po) > 1 for po in decisions)
    assert total - passed >= multiway > 0 and all("definition gives" in f for f in fails)


def test_value_outside_tolerance_fails_and_rounding_passes(decisions):
    def off(vals, po):
        if "hand.equity" in vals:
            vals["hand.equity"] = min(100.0, vals["hand.equity"] + 5)

    def rounded(vals, po):
        if "hand.equity" in vals:
            vals["hand.equity"] = float(round(vals["hand.equity"]))

    p, t, _ = t2.check_t2(_agent(off), decisions)
    assert p == 0 and t == len(decisions)
    p, t, fails = t2.check_t2(_agent(rounded), decisions)
    assert p == t, fails


def test_opp_range_weights_the_heads_up_recomputation(decisions):
    po = next(po for po in decisions if t2._opponents(po) == 1)
    cells = [100.0 if c == "AA" else 0.0 for c in HAND_CLASSES]
    spec = default_agent().spec
    tp = TPVector({"opp.range": cells, "hand.equity": 0.0}, spec)
    e, _ = hu_equity.load()
    i = HAND_CLASSES.index(hand_class(*(card(c) for c in po.hole_cards)))
    assert t2.recompute("hand.equity", tp, po) == pytest.approx(100.0 * e[i, HAND_CLASSES.index("AA")])


def test_an_item_t2_cannot_recompute_fails_instead_of_passing(decisions):
    def emits_foldeq(vals, po):
        vals["plan.foldeq"] = 40.0

    p, t, fails = t2.check_t2(_agent(emits_foldeq), decisions[:2])
    assert t == 4 and p == 2 and all("unsupported" in f for f in fails)


def test_missing_tolerance_is_a_clear_error():
    spec = default_agent().spec
    data = {**spec.data, "grading": {k: v for k, v in spec.data["grading"].items() if k != "t2_tolerance"}}
    with pytest.raises(KeyError, match="t2_tolerance"):
        t2.tolerance(type(spec)(data=data, sha256=spec.sha256, path=spec.path), "hand.equity")


def test_cli_exits_nonzero_when_t2_fails(monkeypatch, capsys):
    def off(vals, po):
        if "hand.equity" in vals:
            vals["hand.equity"] = min(100.0, vals["hand.equity"] + 5)

    monkeypatch.setattr(gate_t, "REGISTRY", {"off": lambda: _agent(off)})
    assert gate_t.main() == 1
    out = capsys.readouterr().out
    assert "T2 [off] 0/" in out and "tp_spec 0.2 sha256" in out


def test_tolerance_is_in_the_spec():
    spec = default_agent().spec
    assert t2.tolerance(spec, "hand.equity") == 1.0 and t2.tolerance(spec, "plan.icm") == 0.5
    assert np.isfinite(t2.tolerance(spec, "hand.outs"))
