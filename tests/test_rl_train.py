import dataclasses
import io
import time

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from referee.gate_l import Report, check_l1  # noqa: E402
from stalker.agents.random_agent import RandomLegalAgent  # noqa: E402
from stalker.rl.train import (  # noqa: E402
    PolicyAgent, Segment, TrainConfig, Trainer, advantages, check_segments, load_policy)
from stalker.tournament.config import load_preset  # noqa: E402
from stalker.tournament.director import run_game  # noqa: E402
from test_rl_env import hyper_sng  # noqa: E402

SMALL = TrainConfig(seed=3, games_per_iter=1, epochs=1, minibatch_segments=6)



def test_random_seats_are_scripted_and_not_trained():
    tr = Trainer(hyper_sng(), dataclasses.replace(SMALL, random_seats=4))
    segs = tr.play_game("g-a")
    assert len(segs) == 2 and len({s.player_id for s in segs}) == 2
    check_segments(segs)


def weights(trainer):
    return {k: v.clone() for k, v in trainer.policy.state_dict().items()}


def test_same_seed_two_steps_same_weights_and_version():
    runs = []
    for _ in range(2):
        tr = Trainer(hyper_sng(), SMALL)
        tr.train_step()
        tr.train_step()
        runs.append((weights(tr), tr.policy_version))
    (w1, v1), (w2, v2) = runs
    assert v1 == v2 and v1.startswith("ai2-i2-")
    assert all(torch.equal(w1[k], w2[k]) for k in w1)
    other = Trainer(hyper_sng(), dataclasses.replace(SMALL, seed=4))
    other.train_step()
    other.train_step()
    assert not all(torch.equal(w1[k], v) for k, v in weights(other).items())


def test_training_changes_weights_and_leaves_global_rng_alone():
    tr = Trainer(hyper_sng(), SMALL)
    before = weights(tr)
    torch.manual_seed(123)
    expected = torch.rand(3)
    torch.manual_seed(123)
    tr.train_step()
    assert torch.equal(torch.rand(3), expected)
    assert not all(torch.equal(before[k], v) for k, v in weights(tr).items())


def test_segments_are_cut_by_game_and_start_from_zero_state():
    tr = Trainer(hyper_sng(), SMALL)
    segs = tr.play_game("g-a") + tr.play_game("g-b")
    check_segments(segs)
    assert {s.game_id for s in segs} == {"g-a", "g-b"}
    assert all(len({o.game_id for o in s.observations}) == 1 for s in segs)
    cfg = hyper_sng()
    for g in ("g-a", "g-b"):  # every player of the game has one segment and money is conserved
        assert sum(s.reward for s in segs if s.game_id == g) == pytest.approx(
            (cfg.prize_pool - cfg.buy_in * cfg.players) / cfg.buy_in)


def test_check_segments_rejects_l6_violations():
    tr = Trainer(hyper_sng(), SMALL)
    a, b = tr.play_game("g-a")[:2], tr.play_game("g-b")[0]
    with pytest.raises(ValueError, match="game_id"):
        check_segments([dataclasses.replace(a[0], observations=a[0].observations + b.observations[:1])])
    with pytest.raises(ValueError, match="zero GRU state"):
        check_segments([dataclasses.replace(a[0], initial_state_zero=False)])
    with pytest.raises(ValueError, match="twice"):
        check_segments([a[0], a[0]])


def test_replay_of_a_segment_ignores_other_segments_in_the_batch():
    """L6 in the update: a segment's recomputed outputs do not depend on what else is batched with it."""
    tr = Trainer(hyper_sng(), SMALL)
    a = tr.play_game("g-a")
    b = tr.play_game("g-b")
    lp_alone, v_alone, _, valid = tr._replay([a[0]])
    lp_mixed, v_mixed, _, _ = tr._replay([a[0], b[0], b[1]])
    n = int(valid[0].sum())
    assert torch.allclose(lp_alone[0, :n], lp_mixed[0, :n], atol=1e-6)
    assert torch.allclose(v_alone[0, :n], v_mixed[0, :n], atol=1e-6)
    # replay starts from zero state, so it reproduces the logps recorded while acting
    assert torch.allclose(lp_alone[0, :n], torch.tensor(a[0].logps), atol=1e-5)


def test_advantages_terminal_reward_only():
    adv, ret = advantages(np.array([0.0, 0.0]), 1.0, gamma=1.0, lam=1.0)
    assert np.allclose(adv, [1.0, 1.0]) and np.allclose(ret, [1.0, 1.0])
    adv, ret = advantages(np.array([0.5]), -1.0, gamma=1.0, lam=0.95)
    assert np.allclose(adv, [-1.5]) and np.allclose(ret, [-1.0])


def test_checkpoint_round_trip_records_policy_version():
    tr = Trainer(hyper_sng(), SMALL)
    tr.train_step()
    buf = io.BytesIO()
    version = tr.save(buf)
    buf.seek(0)
    policy, loaded = load_policy(buf)
    assert loaded == version == tr.policy_version
    assert all(torch.equal(v, policy.state_dict()[k]) for k, v in tr.policy.state_dict().items())


def test_policy_agent_plays_legal_tournament_and_resets_gru():
    tr = Trainer(hyper_sng(), SMALL)
    agent = PolicyAgent(tr.policy, hyper_sng(), np.random.default_rng(0))
    agents = [agent] + [RandomLegalAgent(np.random.default_rng(i)) for i in range(1, 6)]
    res = run_game(hyper_sng(), agents, np.random.default_rng(5), game_id="eval-0")
    assert res.illegal_actions == 0
    assert agent._state is None and agent.memory.game_id is None


def roi_vs_random(policy, games: int, seed: int) -> float:
    cfg = hyper_sng()
    total = 0.0
    for g in range(games):
        seat = g % cfg.players  # rotate the policy's seat so position luck averages out
        agents = [RandomLegalAgent(np.random.default_rng([seed, g, i])) for i in range(cfg.players)]
        agents[seat] = PolicyAgent(policy, cfg, np.random.default_rng([seed, g]))
        res = run_game(cfg, agents, np.random.default_rng([seed, g, 99]), game_id=f"eval-{g}")
        total += res.prizes[seat] - cfg.buy_in
    return total / (games * cfg.buy_in)


@pytest.mark.slow
def test_smoke_cpu_training_beats_random_and_passes_gate_l1():
    """Reference only (small sample, not a strength claim): <=10 min CPU training, then ROI vs random bots > 0."""
    tr = Trainer(hyper_sng(), TrainConfig(seed=0, games_per_iter=8, epochs=2, random_seats=4))
    start = time.monotonic()
    for _ in range(SMOKE_ITERS):
        tr.train_step()
    elapsed = time.monotonic() - start
    roi = roi_vs_random(tr.policy, games=EVAL_GAMES, seed=7)
    print(f"smoke (reference only): {tr.iteration} iterations, {tr.games_played} games, {elapsed:.0f}s, "
          f"version={tr.policy_version}, roi_vs_random={roi:+.3f} over {EVAL_GAMES} games")
    assert elapsed < 600, f"smoke training took {elapsed:.0f}s; the CPU budget is 600s. Lower SMOKE_ITERS."
    assert roi > 0, f"trained policy ROI vs random bots is {roi:+.3f}; expected > 0 after {tr.iteration} iterations."
    for preset in ("6max_sng_wta", "9max_sng_flat"):
        r = Report()
        cfg = load_preset(preset)
        check_l1(lambda: PolicyAgent(tr.policy, cfg, np.random.default_rng(0)), r, presets=(preset,))
        assert r.ok, r.failures


SMOKE_ITERS = 60
EVAL_GAMES = 240
