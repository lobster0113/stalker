from pathlib import Path

import numpy as np
import pytest

from referee.e3 import preflop_probe as P
from stalker.core.cards import hand_class

K5 = 5
SERVED_MID = Path(__file__).resolve().parents[1] / "web" / "app" / "policy" / "mid-6.json"


def _parts(key):
    p = key.split("|")
    return p, int(p[1]), int(p[-1][1:])


def _pick(acts, want):
    for a in want:
        if a in acts:
            return [1.0 if x == a else 0.0 for x in acts]
    return None


def _policy(limp_top: bool):
    """Unopened, the top equity step opens (or, with `limp_top`, limps) and the rest fold. Everyone folds
    to a raise or an all-in, and nobody bets postflop. With `limp_top` the big blind raises any limp, so
    a limp loses the bet while an open takes the blinds: a 2.5bb leak with almost no noise. Without
    it, opening is already the best first action (a limp checks down for less than the blinds)."""
    def pol(key, acts):
        p, street, step = _parts(key)
        free = "f" not in acts
        if free:
            bb_option = street == 0 and p[0] != "call" and p[3] == "0"
            return _pick(acts, ["r"] if (limp_top and bb_option) else ["k", "c"])
        if street > 0 or p[0] == "call" or p[3] != "0" or step < K5 - 1:
            return _pick(acts, ["f"])
        return _pick(acts, ["c"] if limp_top else ["r"])
    return pol


def _table(pol):
    return {"policy": pol, "k": K5, "depth": "full", "players": 3, "menu": "v1", "raise_cap": 3}


def test_group_combos():
    assert len(P.group_combos("AA")) == 6 and len(P.group_combos("AKs")) == 4 and len(P.group_combos("AKo")) == 12
    assert all(hand_class(*c) == "AQs" for c in P.group_combos("AQs"))
    with pytest.raises(ValueError):
        P.group_combos("AX")


def test_probe_flags_a_policy_that_limps_aces():
    r = P.probe(_table(_policy(limp_top=True)), 40, seed=1, spots=("first_in",), seats=[0], groups=("AA",))
    c = r["cells"][0]
    assert c["deals"] == 40 and c["actions"]["c"]["row"] == 1.0
    assert c["leak"] and c["best"] in ("r", "a")
    assert c["open_minus_limp"]["r"]["ci"][0] > 2.0


def test_probe_does_not_flag_a_policy_that_raises_aces():
    r = P.probe(_table(_policy(limp_top=False)), 40, seed=1, spots=("first_in",), seats=[0, 1],
                groups=("AA", "AKo"))
    assert r["leaks"] == 0
    first = r["cells"][0]
    assert first["actions"]["r"]["row"] == 1.0 and first["actions"]["r"]["vs_row_bb"] == 0.0


def test_vs_open_reaches_only_single_raised_pots():
    seen = []

    def spy(key, acts):
        seen.append(key)
        return _policy(False)(key, acts)
    res, tries = P.deals(_table(spy), "vs_open", 2, "AA", 5, np.random.SeedSequence(3))
    assert len(res) == 5 and tries >= 5
    assert all(acts == ("f", "c", "r", "a") for acts, _, _ in res)
    # Gate L: the policy only ever sees TP keys (public items + the hero's own equity step).
    assert seen and all(k.split("|")[-1].startswith("e") for k in seen)


def test_probe_is_reproducible_and_worker_independent():
    # Two chunks (CHUNK deals each) so that workers=2 really splits the cell; chunk seeds depend only on
    # the cell and the chunk index. A loaded policy file, because worker processes must pickle the table.
    t = P.load(SERVED_MID)
    kw = dict(seed=2, spots=("first_in",), seats=[1], groups=("KK",))
    a = P.probe(t, 2 * P.CHUNK, **kw)
    assert a == P.probe(t, 2 * P.CHUNK, **kw)
    assert a == P.probe(t, 2 * P.CHUNK, workers=2, **kw)



def test_probe_flags_the_served_mid_policy_limping_aces():
    # #413 criterion 1 / #391: the served mid policy (average strategy) limps AA first in from HJ/CO most
    # of the time. Pre-registered cells: first_in, HJ and CO, AA, 300 deals, seed 1. If the served file
    # changes and the leak is gone, this fails on purpose: re-register the cells or close #391.
    assert SERVED_MID.exists(), f"{SERVED_MID} missing: the served policy moved; update this test"
    r = P.probe(P.load(SERVED_MID), 300, seed=1, spots=("first_in",), seats=[1, 2], groups=("AA",))
    assert r["leaks"] >= 1, P.table(r)
    assert any(c["open_minus_limp"]["r"]["ci"][0] > 0 for c in r["cells"] if c["leak"]), P.table(r)


def test_flag_needs_both_the_threshold_and_the_corrected_bound():
    def cell(g, se):
        return {"best": "r", "actions": {"r": {"vs_row_bb": g, "vs_row_se": se}, "c": {"vs_row_bb": 0.0, "vs_row_se": 0.0}}}
    cells = [cell(2.0, 0.5), cell(2.0, 1.5), cell(0.4, 0.01)]
    z = P.flag(cells)
    assert z > P.Z95                      # six tests: stricter than a single 95% bound
    assert [c["leak"] for c in cells] == [True, False, False]
