"""ICM-unit LBR (#917): linear to the chip LBR for winner-take-all equal stacks, deterministic, lambda guard, cash path untouched."""
from __future__ import annotations

import json

import numpy as np
import pytest

from referee.e3 import lbr as L
from referee.e3 import tournament_eval as TE
from stalker.agents.e3_policy import PolicyTable
from stalker.e3 import game as G


def folder(key, acts):
    return [1.0 if a == "f" else 0.0 for a in acts] if "f" in acts else None


STACKS = (1500, 1500, 1500)


def test_equal_stacks_winner_take_all_is_the_chip_lbr_over_total_chips_times_prize():
    prize = 7.0
    icm = L.lbr_icm(folder, 0, 20, STACKS, [prize], seed=3)
    chips = L.lbr_hands(folder, 0, 20, 3, n=3, deal=lambda rng: G.deal(rng, 3, stacks=STACKS))[0]
    # Winner-take-all ICM equity is stack/total x prize, so the change is chips/total x prize; the pool fraction drops the prize.
    want = np.array(chips) * G.BB / sum(STACKS)
    got = L.lbr_hands(folder, 0, 20, 3, n=3, deal=lambda rng: G.deal(rng, 3, stacks=STACKS),
                      reward=lambda s: float(G.payoff(s)[0]) / sum(STACKS))[0]
    assert np.allclose(got, want, atol=1e-9)
    assert icm.mean_bb == pytest.approx(float(np.mean(got)), abs=1e-9)


def test_same_input_same_value():
    a = L.lbr_icm(folder, 1, 6, STACKS, [5.0, 3.0], 0.5, seed=9)
    assert a == L.lbr_icm(folder, 1, 6, STACKS, [5.0, 3.0], 0.5, seed=9)


@pytest.mark.parametrize("lam", [-0.1, 1.5])
def test_lambda_outside_zero_one_raises(lam):
    with pytest.raises(ValueError, match="lam"):
        L.lbr_icm(folder, 0, 2, STACKS, [5.0, 3.0], lam)


def test_cash_lbr_is_unchanged_by_the_hooks():
    a = L.lbr_hands(folder, 2, 4, 5, n=4)
    b = L.lbr_hands(folder, 2, 4, 5, n=4, deal=None, reward=None)
    assert a == b and L.lbr(folder, 2, 4, 5, n=4).mean_bb == pytest.approx(float(np.mean(a[0])))


def test_custom_reward_refuses_aivat():
    with pytest.raises(ValueError, match="AIVAT"):
        L.lbr_hands(folder, 0, 2, reward=lambda s: 0.0, aivat_samples=2)


EMPTY = PolicyTable({}, k=5, depth="basic", menu="v1", raise_cap=3)
SPOT = {"preset": "9max_sng_503020", "remaining": 4, "profile": "even", "level_index": 0}


def test_eval_without_the_option_is_schema_1_with_no_lbr_pool():
    out = TE.evaluate_tournament(EMPTY, [SPOT], games=2)
    assert out["schema_version"] == 1 and "lbr_pool" not in out["cells"][0]


def test_eval_with_lbr_hands_records_lbr_pool_and_leaves_the_other_columns_alone():
    base = TE.evaluate_tournament(EMPTY, [SPOT], games=2)
    out = TE.evaluate_tournament(EMPTY, [SPOT], games=2, lbr_hands=3)
    cell = dict(out["cells"][0])
    pool = cell.pop("lbr_pool")
    assert out["schema_version"] == 2 and pool["hands"] == 3 and pool["stage"] == "b" and pool["se"] >= 0
    assert json.dumps(cell, sort_keys=True) == json.dumps(base["cells"][0], sort_keys=True)
    with pytest.raises(ValueError, match="lbr_hands"):
        TE.evaluate_tournament(EMPTY, [SPOT], games=2, lbr_hands=1)
