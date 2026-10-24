import dataclasses

import numpy as np
import pytest

from stalker.rl.env import GAME_END, GAME_START, TournamentEnv
from stalker.tournament.config import BlindLevel, TournamentConfig


def hyper_sng() -> TournamentConfig:
    return TournamentConfig(
        name="6max hyper SNG", players=6, table_size=6, starting_stack=500,
        levels=(BlindLevel(10, 20, 0, 3), BlindLevel(25, 50, 0, 3), BlindLevel(50, 100, 0, 3),
                BlindLevel(100, 200, 0, 3), BlindLevel(200, 400, 0, 3), BlindLevel(500, 1000, 0, 3)),
        payouts=(0.5, 0.3, 0.2), buy_in=100)


def play(env: TournamentEnv, seed: int, policy_seed: int):
    """Random policy over the legal mask; returns (final StepResult, all step results)."""
    pol = np.random.default_rng(policy_seed)
    res = env.reset(np.random.default_rng(seed))
    out = [res]
    while not res.done:
        res = env.step(int(pol.choice([i for i, m in enumerate(res.action_mask) if m])))
        out.append(res)
    return res, out


def test_boundary_events_once_per_tournament():
    env = TournamentEnv(hyper_sng())
    res, out = play(env, 1, 2)
    events = [e for r in out for e in r.events]
    assert events.count(GAME_START) == 1 and events.count(GAME_END) == 1
    assert out[0].events == (GAME_START,) and res.events == (GAME_END,)


def test_same_seed_same_actions_same_trajectory():
    def traj(env):
        _, out = play(env, 7, 8)
        return [(r.player_id, r.observation, r.rewards) for r in out]
    assert traj(TournamentEnv(hyper_sng())) == traj(TournamentEnv(hyper_sng()))


def test_rewards_conserve_money_over_100_tournaments():
    cfg = hyper_sng()
    env = TournamentEnv(cfg)
    for seed in range(100):
        res, out = play(env, seed, seed + 1000)
        assert all(r.rewards == (0.0,) * 6 for r in out[:-1])
        assert sum(res.rewards) == pytest.approx(-cfg.buy_in * cfg.players + sum(res.result.prizes))
        assert sum(res.result.prizes) == pytest.approx(cfg.prize_pool)
        assert res.result.illegal_actions == 0


def test_masked_action_rejected_and_mask_matches_legal():
    env = TournamentEnv(hyper_sng())
    pol = np.random.default_rng(0)
    seen_masked = {"fold": False, "raise": False}
    for seed in range(5):
        res = env.reset(np.random.default_rng(seed))
        while not res.done and not all(seen_masked.values()):
            lg = res.observation.legal
            assert res.action_mask[0] == lg["fold"] and res.action_mask[1] == lg["call"]
            assert set(res.action_mask[2:]) == {lg["raise"]}
            for name, idx in (("fold", 0), ("raise", 2)):
                if not res.action_mask[idx]:
                    seen_masked[name] = True
                    with pytest.raises(ValueError, match="not legal"):
                        env.step(idx)
            res = env.step(int(pol.choice([i for i, m in enumerate(res.action_mask) if m])))
        if all(seen_masked.values()):
            break
    assert all(seen_masked.values()), "no masked fold/raise decision was reached"
    for bad in (-1, env.n_actions):
        with pytest.raises(ValueError, match="not legal"):
            env.step(bad)
    env.close()


def test_raise_sizes_stay_in_legal_range():
    env = TournamentEnv(hyper_sng(), raise_pot_fractions=(0.1, 3.0))
    res = env.reset(np.random.default_rng(4))
    lg = res.observation.legal
    for i in range(2, env.n_actions):
        a = env._to_action(res.observation, i)
        assert lg["min_raise_to"] <= a.amount <= lg["max_raise_to"]
    assert env._to_action(res.observation, env.n_actions - 1).amount == lg["max_raise_to"]
    env.close()


def test_reset_midgame_and_step_after_done():
    env = TournamentEnv(hyper_sng())
    env.reset(np.random.default_rng(1))
    res, _ = play(env, 2, 3)  # reset aborts the unfinished game
    with pytest.raises(RuntimeError):
        env.step(1)
    assert dataclasses.is_dataclass(res.result)


def test_observation_only_hero_cards():
    env = TournamentEnv(hyper_sng())
    res = env.reset(np.random.default_rng(5))
    assert len(res.observation.hole_cards) == 2
    env.close()
