import numpy as np

from stalker.e3.chart import chart
from stalker.e3.mccfr import E3MCCFR


def test_chart_rows_are_distributions_and_children_exist():
    m = E3MCCFR(1, 5, 6, "basic")
    m.iterate(3)
    sp = chart(m.current_policy(), max_nodes=12, lbr_bb=1.0)
    assert sp["exact"] is False and sp["nodes"][""]["seat"] == "UTG"
    decisions = [n for n in sp["nodes"].values() if "terminal" not in n]
    assert 1 <= len(decisions) <= 12
    for n in decisions:
        a = np.array(n["strategy"]["tp_beginner"])
        assert a.shape == (169, len(n["actions"])) and np.allclose(a.sum(axis=1), 1, atol=2e-3)
        assert all(c in sp["nodes"] for c in n["next"].values())


def test_untrained_policy_gives_uniform_rows():
    sp = chart({}, max_nodes=1)
    a = np.array(sp["nodes"][""]["strategy"]["tp_beginner"])
    assert np.allclose(a, 1 / a.shape[1], atol=2e-3)
