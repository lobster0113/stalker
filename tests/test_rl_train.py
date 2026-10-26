import dataclasses
import io
import time

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from referee.gate_l import Report, check_l1  # noqa: E402
from stalker.agents.random_agent import RandomLegalAgent  # noqa: E402
from stalker.rl.evaluate import ACTION_KINDS, evaluate  # noqa: E402
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


def test_reference_seats_play_inside_the_game_and_are_not_trained():
    tr = Trainer(hyper_sng(), dataclasses.replace(SMALL, random_seats=2, reference_seats=2))
    for g in ("g-a", "g-b"):
        segs = tr.play_game(g)
        assert len(segs) == 2  # 6 players - 2 random - 2 reference
        check_segments(segs)


def test_past_checkpoints_fill_the_pool_and_their_seats_are_not_trained():
    cfg = dataclasses.replace(SMALL, past_checkpoints=1, past_checkpoint_p=1.0, past_pool_size=2)
    tr = Trainer(hyper_sng(), cfg)
    assert len(tr.play_game("g-0")) == 6  # empty pool: pure self-play
    for _ in range(3):
        tr.train_step()
    assert len(tr.past_pool) == 2
    assert all(not p.requires_grad for snap in tr.past_pool for p in snap.parameters())
    snap = {k: v.clone() for k, v in tr.past_pool[-1].state_dict().items()}
    assert all(torch.equal(snap[k], v) for k, v in tr.policy.state_dict().items())
    segs = tr.play_game("g-1")
    assert len(segs) == 1  # p=1: every seat but one learner seat is a past snapshot
    tr.train_step()
    assert all(torch.equal(snap[k], v) for k, v in tr.past_pool[-2].state_dict().items())  # frozen copy


def test_opponent_pool_rejects_configs_without_a_learning_seat():
    with pytest.raises(ValueError, match="no learning seat"):
        Trainer(hyper_sng(), dataclasses.replace(SMALL, random_seats=3, reference_seats=3))


def test_same_seed_two_steps_same_weights_with_opponent_pool():
    cfg = dataclasses.replace(SMALL, random_seats=1, reference_seats=1, past_checkpoints=1, past_checkpoint_p=0.5)
    runs = []
    for _ in range(2):
        tr = Trainer(hyper_sng(), cfg)
        tr.train_step()
        tr.train_step()
        runs.append(weights(tr))
    assert all(torch.equal(runs[0][k], runs[1][k]) for k in runs[0])


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


@pytest.fixture(scope="module")
def smoke():
    """Reference only (small sample, not a strength claim): <=10 min CPU training, evaluated vs random bots with the
    check/fold baseline. ROI is reported, not asserted: check/fold alone earns about +0.75 there (#78)."""
    tr = Trainer(hyper_sng(), TrainConfig(seed=0, games_per_iter=8, epochs=2, random_seats=4))
    start = time.monotonic()
    for _ in range(SMOKE_ITERS):
        tr.train_step()
    elapsed = time.monotonic() - start
    ev = evaluate(tr.policy, hyper_sng(), games=EVAL_GAMES, seed=7)
    print(f"smoke (reference only): {tr.iteration} iterations, {tr.games_played} games, {elapsed:.0f}s, "
          f"version={tr.policy_version}, roi_vs_random={ev.roi:+.3f} (check/fold {ev.baseline_roi:+.3f}) "
          f"over {EVAL_GAMES} games, fold_rate={ev.fold_rate:.3f} of {ev.facing_bet}, actions={ev.actions}")
    return tr, elapsed, ev


@pytest.mark.slow
def test_smoke_cpu_training_records_actions_and_passes_gate_l1(smoke):
    tr, elapsed, ev = smoke
    assert elapsed < 600, f"smoke training took {elapsed:.0f}s; the CPU budget is 600s. Lower SMOKE_ITERS."
    assert ev.decisions > 0 and ev.facing_bet > 0 and set(ev.actions) == set(ACTION_KINDS), ev.actions
    for preset in ("6max_sng_wta", "9max_sng_flat"):
        r = Report()
        cfg = load_preset(preset)
        check_l1(lambda: PolicyAgent(tr.policy, cfg, np.random.default_rng(0)), r, presets=(preset,))
        assert r.ok, r.failures


# strict: once training stops collapsing this XPASSes and fails CI, so whoever fixes it (#91) must drop the mark.
@pytest.mark.xfail(strict=True, reason="known check/fold collapse of the smoke training (#78, #88); #91 fixes it")
@pytest.mark.slow
def test_smoke_cpu_training_does_not_collapse_to_check_fold(smoke):
    tr, _, ev = smoke
    assert ev.fold_rate < 0.95, (
        f"trained policy folds {ev.fold_rate:.3f} of {ev.facing_bet} decisions facing a bet after {tr.iteration} "
        "iterations: it collapsed to check/fold. Fix the training (see docs/research/2026-10-rl-opponent-pool.md), "
        "not this threshold.")


SMOKE_ITERS = 60
EVAL_GAMES = 240
