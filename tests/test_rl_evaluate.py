import numpy as np
import pytest

torch = pytest.importorskip("torch")
from stalker.rl.evaluate import ACTION_KINDS, evaluate, seat_roi  # noqa: E402
from stalker.rl.policy import Policy, PolicyConfig  # noqa: E402
from stalker.agents.check_fold import CheckFoldAgent  # noqa: E402
from test_rl_env import hyper_sng  # noqa: E402

FOLD, CALL = 0, 1


def biased_policy(index: int) -> Policy:
    """A policy that picks action `index` with probability ~1 whenever it is legal (a collapsed dummy)."""
    p = Policy(PolicyConfig(), seed=0)
    with torch.no_grad():
        p.actor.weight.zero_()
        p.actor.bias.fill_(-50.0)
        p.actor.bias[index] = 50.0
        p.actor.bias[CALL] = max(float(p.actor.bias[CALL]), 0.0)  # check/call when the favoured action is masked
    return p


def test_evaluate_reports_paired_baseline_and_action_distribution():
    cfg = hyper_sng()
    ev = evaluate(Policy(PolicyConfig(), seed=1), cfg, games=6, seed=11)
    assert ev.decisions > 0 and set(ev.actions) == set(ACTION_KINDS)
    assert sum(ev.actions.values()) == pytest.approx(1.0)
    assert (ev.baseline_roi, ev.baseline_se) == seat_roi(lambda rng: CheckFoldAgent(), cfg, "random", 6, 11)
    assert ev == evaluate(Policy(PolicyConfig(), seed=1), cfg, games=6, seed=11)  # same seed, same deals and actions


@pytest.mark.parametrize("opponent", ["random", "reference"])
def test_fold_rate_criterion_catches_a_check_fold_collapse(opponent):
    ev = evaluate(biased_policy(FOLD), hyper_sng(), games=6, seed=11, opponent=opponent)
    assert ev.facing_bet > 0 and ev.fold_rate >= 0.95, (ev.fold_rate, ev.actions)
    if opponent == "random":  # why fold_rate counts only decisions facing a bet: here many checks are free
        assert ev.actions["fold"] < 0.95


def test_fold_rate_criterion_passes_a_policy_that_does_not_fold():
    ev = evaluate(biased_policy(CALL), hyper_sng(), games=6, seed=11)
    assert ev.facing_bet > 0 and ev.fold_rate < 0.05 and ev.actions["check_call"] > 0.95, (ev.fold_rate, ev.actions)


def test_evaluate_rejects_unknown_opponent():
    with pytest.raises(ValueError, match="opponent must be one of"):
        evaluate(biased_policy(CALL), hyper_sng(), games=2, seed=0, opponent="humans")
