import json

import numpy as np

from stalker.core.cards import cards
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.tools import preflop_ev as P


def table(policy, k=5, depth="full"):
    return {"policy": policy, "k": k, "depth": depth, "players": 6, "menu": "v1", "raise_cap": G.RAISE_CAP}


def folder(key, acts):
    # Folds whenever it can, else checks: nobody but the tested seat ever puts in a chip.
    pick = next(a for a in ("f", "k", "c") if a in acts)
    return [1.0 if a == pick else 0.0 for a in acts]


def test_raise_against_a_folding_table_wins_exactly_the_blinds():
    r = P.action_values(table(folder), seat=3, hand="AhQh", hands=20, seed=1)
    assert r["actions"] == ["f", "c", "r", "a"]
    ev = dict(zip(r["actions"], r["ev_bb"]))
    assert ev["f"] == 0.0 and ev["r"] == 1.5 and ev["a"] == 1.5
    # The folding policy's own row is fold, so raising beats it by the blinds on every deal.
    assert r["best"] in ("r", "a") and r["regret_bb"] == 1.5 and r["regret_se"] == 0.0


def test_small_blind_fold_loses_its_blind():
    r = P.action_values(table(folder), seat=4, hand="7c2d", hands=10, seed=2)
    assert dict(zip(r["actions"], r["ev_bb"]))["f"] == -0.5


def test_seeded_and_independent_of_workers(monkeypatch):
    monkeypatch.setattr(P, "CHUNK", 4)   # two chunks, so the worker split could matter
    t = table({})
    a = P.action_values(t, 3, "AsAd", hands=8, seed=5)
    assert a == P.action_values(t, 3, "AsAd", hands=8, seed=5)
    assert a == P.action_values(t, 3, "AsAd", hands=8, seed=5, workers=2)
    assert a != P.action_values(t, 3, "AsAd", hands=8, seed=6)


def test_the_seat_holds_the_hand_and_no_card_repeats():
    t = table({})
    pool = P.hand_pool(t, 3, "AhQh")
    rng = np.random.default_rng(0)
    for _ in range(20):
        s = P._deal(rng, 6, 3, pool[0], t)
        assert s.hole[3] == tuple(cards("AhQh"))
        dealt = [c for h in s.hole for c in h] + list(s.deck)
        assert sorted(dealt) == list(range(52))


def test_a_step_pool_is_the_combos_of_that_step_at_the_spot():
    t = table({})
    s, ranges = P.first_in(t, 3)
    steps = K.equity_steps(s, 3, ranges, 5)
    pool = P.hand_pool(t, 3, "e4")
    assert len(pool) == int((steps == 4).sum()) > 0
    r = P.action_values(t, 3, "e4", hands=10, seed=3)
    assert r["steps"] == [4] and r["by_step"]["e4"]["deals"] == 10
    assert len(P.hand_pool(t, 3, "any")) == 1326


def test_loads_the_web_policy_file_and_reads_its_scale(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"schema": "stalker.web.policy", "k": 11, "depth": "full", "players": 6, "q": 255,
                             "policy": {"3|0|2|0|0|4|0|fcra|e10": [0, 255, 0, 0]}}), encoding="utf-8")
    t = P.load(f)
    assert t["policy"]["3|0|2|0|0|4|0|fcra|e10"] == [0.0, 1.0, 0.0, 0.0] and t["menu"] == "v1"
