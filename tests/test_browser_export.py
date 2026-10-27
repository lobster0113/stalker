import numpy as np
import pytest

from referee.anchors import pushfold as P
from stalker.browser import export as X


@pytest.fixture(scope="module")
def spots():
    return [X.hu_pushfold(10.0, tiers=False), X.hu_open_shove(20.0, iters=800), X.three_handed_icm(10.0, tiers=False),
            X.icm_pushfold(10.0, (0.65, 0.35), 6, tiers=False)]


def test_every_strategy_row_is_a_distribution_and_ev_matches_actions(spots):
    for sp in spots:
        for nid, n in sp["nodes"].items():
            if "terminal" in n:
                continue
            for name, rows in n["strategy"].items():
                a = np.array(rows)
                assert a.shape == (169, len(n["actions"])) and np.allclose(a.sum(axis=1), 1, atol=2e-3), (sp["id"], nid, name)
            assert np.array(n["ev"]).shape == (169, len(n["actions"]))
            assert all(c in sp["nodes"] for c in n["next"].values()), (sp["id"], nid)


def test_child_reach_is_parent_reach_times_the_action_frequency(spots):
    for sp in spots:
        nodes = sp["nodes"]
        for nid, n in nodes.items():
            if "terminal" in n:
                continue
            gto = np.array(n["strategy"]["gto"])
            for i, a in enumerate(n["actions"]):
                child = nodes[n["next"][a]]
                if "terminal" in child:
                    continue
                want = np.array(n["reach"][n["seat"]]) * gto[:, i]
                assert np.allclose(child["reach"][n["seat"]], want, atol=2e-3), (sp["id"], nid, a)


def test_push_fold_spot_is_the_cached_equilibrium(spots):
    push, call = P.strategy(10.0, 0.0)
    sp = spots[0]
    assert np.allclose(np.array(sp["nodes"][""]["strategy"]["gto"])[:, 1], push, atol=1e-3)
    assert np.allclose(np.array(sp["nodes"]["a"]["strategy"]["gto"])[:, 1], call, atol=1e-3)
    # The GTO action is never much worse than the alternative in the exported EVs.
    ev = np.array(sp["nodes"][""]["ev"])
    assert np.all(np.where(push > 0.99, ev[:, 1] >= ev[:, 0] - 0.01, True))


def test_icm_aces_always_move_in(spots):
    assert spots[2]["nodes"][""]["strategy"]["gto"][0][1] > 0.99


def test_six_handed_tree_has_every_first_in_and_caller_node(spots):
    nodes = spots[3]["nodes"]
    # First-in decisions for UTG..SB (5) plus, for each pusher p, callers p+1..BB.
    decisions = [n for n in nodes.values() if "terminal" not in n]
    assert len(decisions) == 5 + sum(6 - (p + 1) for p in range(5))
    assert nodes[""]["seat"] == "UTG" and nodes["f-f-f-f-f"]["terminal"].startswith("모두 폴드")
