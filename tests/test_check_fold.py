import numpy as np

from stalker.agents.base import Agent
from stalker.agents.check_fold import CheckFoldAgent
from stalker.agents.random_agent import RandomLegalAgent
from stalker.tournament.config import load_preset
from stalker.tournament.director import run_game


class _Recorder(Agent):
    def __init__(self, inner: Agent, log: list) -> None:
        self.inner, self.log = inner, log

    def act(self, observation):
        action = self.inner.act(observation)
        self.log.append((observation.legal, action))
        return action


def _play(seed: int):
    cfg = load_preset("6max_sng_wta")
    log: list = []
    agents = [_Recorder(CheckFoldAgent(), log)]
    agents += [RandomLegalAgent(np.random.default_rng([seed, i])) for i in range(1, 6)]
    return run_game(cfg, agents, np.random.default_rng(seed), game_id="cf"), log


def test_check_fold_checks_when_free_and_folds_to_any_bet():
    res, log = _play(3)
    assert res.illegal_actions == 0
    assert any(la.call_amount == 0 for la, _ in log) and any(la.call_amount > 0 for la, _ in log)
    for la, action in log:
        if la.call_amount > 0 and la.can_fold:
            assert action.kind == "fold"
        else:
            assert action.kind == "call"


def test_check_fold_is_deterministic():
    (a, log_a), (b, log_b) = _play(5), _play(5)
    assert a.prizes == b.prizes and [x for _, x in log_a] == [x for _, x in log_b]
