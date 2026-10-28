import copy
from pathlib import Path

import numpy as np
import pytest

from referee import gate_t
from stalker.env.contract import decision_context
from stalker.tp import bottleneck as B
from stalker.tp.spec import Spec, load

ROOT = Path(__file__).resolve().parent.parent


class _PeekingAgent(B.BottleneckAgent):
    """Reads opponent stats straight from the observation: a bottleneck bypass T1 must catch."""

    def action_distribution(self, po, tp=None):
        d = super().action_distribution(po, tp)
        hands = sum(s.hands_seen for s in po.seats if s.used)
        if "fold" in d and hands % 2:
            return {a: (1.0 if a == "fold" else 0.0) for a in d}
        return d


def test_t1_passes_for_the_registered_bottleneck_agent():
    p, t, fails = gate_t.check_t1(B.default_agent())
    assert p == t == gate_t.T1_DECISIONS and not fails


def test_t1_catches_an_agent_that_reads_raw_observations():
    a = B.default_agent()
    p, t, fails = gate_t.check_t1(_PeekingAgent(a.head, a.action_head, a.spec))
    assert p < t and "DecisionContext" in fails[0]


def test_agent_output_depends_on_the_tp_vector():
    # T1 is only meaningful if the TP actually drives the action.
    agent = B.default_agent()
    po = gate_t._observations()[0]
    lo = B.TPVector({"hand.equity": 5.0}, agent.spec)
    hi = B.TPVector({"hand.equity": 95.0}, agent.spec)
    assert agent.action_distribution(po, lo) != agent.action_distribution(po, hi)


def test_distribution_covers_legal_actions_only():
    agent = B.default_agent()
    for po in gate_t._observations():
        d = agent.action_distribution(po)
        assert set(d) == set(decision_context(po).legal_actions) and sum(d.values()) == pytest.approx(1.0)


def test_item_list_comes_from_the_spec():
    spec = load()
    data = copy.deepcopy(spec.data)
    data["items"].append({"id": "opp.extra", "module": "common", "kind": "judgment", "question": "?", "ends": None,
                          "scale": "0-100", "applies": "always", "na": None, "eligible_for_grading": True,
                          "grading_condition": "always"})
    wider = Spec(data, "x", spec.path)
    assert B.tp_items(wider) == B.tp_items(spec) + ["opp.extra"]
    n = B.LinearBottleneck.init(wider, np.random.default_rng(0)).weights.shape[1]
    assert n == B.LinearBottleneck.init(spec, np.random.default_rng(0)).weights.shape[1] + 2
    assert "plan.pot" not in B.tp_items(spec) and "act.choice" not in B.tp_items(spec)


def test_tp_vector_validates_items_and_scale():
    spec = load()
    with pytest.raises(ValueError, match="not in spec"):
        B.TPVector({"opp.bluff": 50}, spec)
    with pytest.raises(ValueError, match="0-100"):
        B.TPVector({"hand.equity": 120}, spec)
    assert B.TPVector({}, spec)["hand.equity"] is None


def test_linear_head_is_seeded():
    spec = load()
    a = B.LinearBottleneck.init(spec, np.random.default_rng(3)).weights
    b = B.LinearBottleneck.init(spec, np.random.default_rng(3)).weights
    assert np.array_equal(a, b)


def test_gates_md_t1_matches_implementation():
    gates = (ROOT / "referee" / "GATES.md").read_text(encoding="utf-8")
    line = next(x for x in gates.splitlines() if x.startswith("- T1 "))
    assert f"N={gate_t.T1_PERTURBATIONS}" in line and "check_t1" in line


def test_tp_vector_holds_every_spec_scale_and_encodes_them():
    # #232 review: opp.range is a 169-cell range (scale range_169), plan.icm is in percentage points.
    import copy
    import dataclasses

    import numpy as np

    from stalker.tp import bottleneck as B
    from stalker.tp.spec import load

    spec = load()
    tp = B.TPVector({"opp.range": [50.0] * 169, "plan.icm": -3.5, "hand.equity": 62.0}, spec)
    assert tp["opp.range"] == (50.0,) * 169 and tp["plan.icm"] == -3.5 and tp["hand.equity"] == 62.0
    with pytest.raises(ValueError, match="needs 169 values"):
        B.TPVector({"opp.range": [50.0] * 13}, spec)
    with pytest.raises(ValueError, match="outside 0..100"):
        B.TPVector({"opp.range": [150.0] * 169}, spec)

    class DC:  # only the numeric facts encode reads
        pass

    dc = DC()
    for f in B.DC_NUMERIC:
        setattr(dc, f, 1.0)
    feats = B.encode(tp, dc)
    assert len(feats) == B.feature_count(spec)
    assert len(feats) == sum(B.item_scale(spec, i)[0] + 1 for i in B.tp_items(spec)) + len(B.DC_NUMERIC)
    assert int(np.isclose(feats, 0.5).sum()) == 169  # the range's cells, encoded value/100

    fake = copy.deepcopy(spec.data)
    next(i for i in fake["items"] if i["id"] == "hand.equity")["scale"] = "hexagon"
    with pytest.raises(ValueError, match="SCALES"):
        B.TPVector({}, dataclasses.replace(spec, data=fake))


def test_dc_features_must_exist_in_the_spec():
    import copy
    import dataclasses

    import numpy as np

    from stalker.tp import bottleneck as B
    from stalker.tp.spec import load

    spec = load()
    B.check_dc_fields(spec)
    fake = copy.deepcopy(spec.data)
    fake["decision_context"] = [f for f in fake["decision_context"] if f != "spr"]
    with pytest.raises(ValueError, match="spr"):
        B.LinearBottleneck.init(dataclasses.replace(spec, data=fake), np.random.default_rng(0))
