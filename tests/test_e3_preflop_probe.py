import numpy as np
import pytest

from referee.e3 import preflop_probe as P
from stalker.core.cards import hand_class

K5 = 5


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
    t = _table(_policy(limp_top=True))
    a = P.probe(t, 6, seed=2, spots=("first_in",), seats=[1], groups=("KK",))
    assert a == P.probe(t, 6, seed=2, spots=("first_in",), seats=[1], groups=("KK",))


def test_flag_needs_both_the_threshold_and_the_corrected_bound():
    def cell(g, se):
        return {"best": "r", "actions": {"r": {"vs_row_bb": g, "vs_row_se": se}, "c": {"vs_row_bb": 0.0, "vs_row_se": 0.0}}}
    cells = [cell(2.0, 0.5), cell(2.0, 1.5), cell(0.4, 0.01)]
    z = P.flag(cells)
    assert z > P.Z95                      # six tests: stricter than a single 95% bound
    assert [c["leak"] for c in cells] == [True, False, False]
