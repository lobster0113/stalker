
import numpy as np
import pytest

torch = pytest.importorskip("torch")
from referee.gate_l import Report, check_l1  # noqa: E402
from stalker.agents.random_agent import RandomLegalAgent  # noqa: E402
from stalker.rl import candidate  # noqa: E402
from stalker.rl.train import TrainConfig, Trainer  # noqa: E402
from stalker.tournament.config import load_preset  # noqa: E402
from stalker.tournament.director import run_game  # noqa: E402
from test_rl_env import hyper_sng  # noqa: E402


@pytest.fixture(scope="module")
def checkpoint(tmp_path_factory):
    tr = Trainer(hyper_sng(), TrainConfig(seed=3, games_per_iter=1, epochs=1, minibatch_segments=6,
                                          raise_pot_fractions=(0.5, 1.0, 2.0)))
    tr.train_step()
    path = tmp_path_factory.mktemp("ckpt") / "policy.pt"
    return path, tr.save(path)


def test_missing_checkpoint_errors_say_how_to_fix(tmp_path, monkeypatch):
    monkeypatch.delenv(candidate.CHECKPOINT_ENV, raising=False)
    with pytest.raises(ValueError, match=candidate.CHECKPOINT_ENV):
        candidate.policy(load_preset("6max_sng_wta"))
    with pytest.raises(FileNotFoundError, match="Trainer.save"):
        candidate.policy(load_preset("6max_sng_wta"), tmp_path / "nope.pt")


def test_factory_exposes_version_and_uses_trained_fractions(checkpoint, monkeypatch):
    path, version = checkpoint
    monkeypatch.setenv(candidate.CHECKPOINT_ENV, str(path))
    make = candidate.policy(load_preset("6max_sng_wta"))
    assert make.policy_version == version
    assert make(np.random.default_rng(0)).fractions == (0.5, 1.0, 2.0)


def _actions(make, seed):
    cfg = load_preset("6max_sng_wta")
    agents = [make(np.random.default_rng([seed, 0]))] + [RandomLegalAgent(np.random.default_rng(i)) for i in range(1, 6)]
    events = []
    run_game(cfg, agents, np.random.default_rng(11), observer=events.append, game_id="cand-0")
    return [(e.data["action"], e.data["amount"]) for e in events if e.type == "ACTION" and e.data["player_id"] == 0]


def test_same_checkpoint_and_seed_same_actions(checkpoint):
    path, _ = checkpoint
    cfg = load_preset("6max_sng_wta")
    a, b = (_actions(candidate.policy(cfg, path), 1) for _ in range(2))
    assert a and a == b


def test_memory_is_per_game_gate_l1(checkpoint):
    path, _ = checkpoint
    cfg = load_preset("6max_sng_wta")
    make = candidate.policy(cfg, path)
    r = Report()
    check_l1(lambda: make(np.random.default_rng(0)), r, presets=("6max_sng_wta",))
    assert r.ok, r.failures
