import dataclasses

import numpy as np
import pytest

from referee.gate_r.checks import Tally, check_game
from stalker.agents.random_agent import RandomLegalAgent
from stalker.tournament.config import load_preset
from stalker.tournament.director import run_game
from stalker.tournament.start_state import (STACK_PROFILES, StartState, make_start_state, tournament_stage,
                                            validate_start_state)


def _play(cfg, ss, seed=0):
    events = []
    agents = [RandomLegalAgent(np.random.default_rng([seed, i])) for i in range(cfg.players)]
    res = run_game(cfg, agents, np.random.default_rng(seed), observer=events.append, start_state=ss)
    return res, events


@pytest.mark.parametrize("profile", STACK_PROFILES)
def test_make_start_state_is_deterministic_and_conserves_chips(profile):
    cfg = load_preset("9max_sng_flat")
    a = make_start_state(cfg, np.random.default_rng(5), 4, profile, 2)
    b = make_start_state(cfg, np.random.default_rng(5), 4, profile, 2)
    assert a == b
    assert a.remaining == 4 and a.eliminated == cfg.players - 4 and a.level_index == 2
    assert sum(a.stacks.values()) == cfg.starting_stack * cfg.players
    assert all(c > 0 for c in a.stacks.values())
    assert make_start_state(cfg, np.random.default_rng(6), 4, profile, 2) != a


def test_even_profile_splits_evenly():
    cfg = load_preset("9max_sng_flat")
    ss = make_start_state(cfg, np.random.default_rng(0), 3, "even")
    assert sorted(ss.stacks.values()) == [cfg.starting_stack * 3] * 3


@pytest.mark.parametrize("bad", [
    dict(stacks={0: 100, 1: 100}),  # sum != total
    dict(stacks={0: 0, 1: 3000}),
    dict(stacks={0: 1500, 99: 1500}),
    dict(eliminated=3),
    dict(level_index=99),
    dict(button=99),
])
def test_validate_rejects_bad_states(bad):
    cfg = dataclasses.replace(load_preset("9max_sng_flat"), players=2, table_size=2, payouts=(1.0,))
    total = cfg.starting_stack * 2
    good = StartState({0: total // 2, 1: total - total // 2}, 0, 0, 0)
    validate_start_state(cfg, good)
    with pytest.raises(ValueError):
        validate_start_state(cfg, dataclasses.replace(good, **bad))


def test_run_game_from_start_state_ranks_and_pays_by_hand():
    cfg = load_preset("9max_sng_flat")  # 9 players, 3 paid equally
    total = cfg.starting_stack * cfg.players
    ss = StartState({2: total // 2, 5: total - total // 2}, 7, 0, 0)
    res, events = _play(cfg, ss)
    assert sorted(res.ranks[p] for p in (2, 5)) == [1, 2]
    assert [res.ranks[p] for p in (0, 1, 3, 4, 6, 7, 8)] == [3, 4, 5, 6, 7, 8, 9]
    pay = cfg.payout_amounts()
    assert res.prizes[2] + res.prizes[5] == pay[0] + pay[1]
    assert res.prizes[0] == pay[2] and res.prizes[1] == 0.0
    sat = {p for e in events if e.type == "NEW_HAND" for p in e.data["seat_players"].values()}
    assert sat == {2, 5}
    tally = check_game(cfg, events, res, start_state=ss)
    assert tally.pass_rate == 1.0 and not tally.failures


def test_level_index_sets_blinds_hands_and_minutes():
    cfg = load_preset("9max_sng_flat")
    ss = make_start_state(cfg, np.random.default_rng(1), 3, "random", 3)
    _, events = _play(cfg, ss)
    first = next(e for e in events if e.type == "NEW_HAND")
    assert first.data["level_index"] == 3
    lv = cfg.levels[3]
    assert (first.data["sb"], first.data["bb"]) == (lv.sb, lv.bb)
    mcfg = dataclasses.replace(cfg, length_unit="minutes",
                               levels=tuple(dataclasses.replace(x, length=5) for x in cfg.levels))
    ss = make_start_state(mcfg, np.random.default_rng(1), 3, "random", 3)
    res, events = _play(mcfg, ss)
    assert next(e for e in events if e.type == "NEW_HAND").data["level_index"] == 3
    assert check_game(mcfg, events, res, start_state=ss).pass_rate == 1.0


@pytest.mark.parametrize("preset,remaining", [("9max_sng_flat", 4), ("mtt54", 20), ("6max_sng_wta", 2)])
@pytest.mark.parametrize("seed", range(3))
def test_gate_r_passes_on_mid_start_games(preset, remaining, seed):
    cfg = load_preset(preset)
    ss = make_start_state(cfg, np.random.default_rng(seed), remaining, "skewed", 1)
    res, events = _play(cfg, ss, seed)
    tally = check_game(cfg, events, res, start_state=ss)
    assert tally.pass_rate == 1.0, tally.failures


def test_gate_r_fails_when_start_stacks_are_one_chip_off():
    cfg = load_preset("9max_sng_flat")
    ss = make_start_state(cfg, np.random.default_rng(0), 4, "random", 0)
    res, events = _play(cfg, ss)
    p = next(iter(ss.stacks))
    bad = dataclasses.replace(ss, stacks={**ss.stacks, p: ss.stacks[p] + 1})
    tally = check_game(cfg, events, res, Tally(), start_state=bad)
    assert tally.pass_rate < 1.0
    with pytest.raises(ValueError):
        run_game(cfg, [RandomLegalAgent(np.random.default_rng(i)) for i in range(cfg.players)],
                 np.random.default_rng(0), start_state=bad)


@pytest.mark.parametrize("remaining,want", [
    (9, "final_table"), (6, "final_table"), (5, "bubble_near"), (4, "bubble_near"), (3, "in_the_money"), (1, "in_the_money"),
])
def test_stage_9max_sng_three_paid(remaining, want):
    assert tournament_stage(remaining, 3, 9, 9) == want


@pytest.mark.parametrize("remaining,want", [
    (180, "early"), (135, "early"), (134, "middle"), (28, "middle"), (27, "bubble_near"), (19, "bubble_near"),
    (18, "in_the_money"), (10, "in_the_money"),
])
def test_stage_mtt_180_players_18_paid(remaining, want):
    assert tournament_stage(remaining, 18, 9, 180) == want


def test_stage_final_table_when_unpaid_tail_is_short():
    assert tournament_stage(9, 18, 9, 180) == "in_the_money"
    assert tournament_stage(9, 2, 9, 180) == "final_table"
    assert tournament_stage(3, 2, 9, 180) == "bubble_near"


def test_stage_rejects_bad_arguments():
    with pytest.raises(ValueError):
        tournament_stage(0, 3, 9, 9)
