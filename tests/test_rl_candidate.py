import json
import os
import subprocess
import sys

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from referee.gate_b.runner import INSUFFICIENT  # noqa: E402
from referee.gate_l import Report, check_l1  # noqa: E402
from stalker.agents.random_agent import RandomLegalAgent  # noqa: E402
from stalker.rl import candidate  # noqa: E402
from stalker.rl.train import TrainConfig, Trainer  # noqa: E402
from stalker.tournament.config import load_preset  # noqa: E402
from stalker.tournament.director import run_game  # noqa: E402
from test_rl_env import hyper_sng  # noqa: E402

SPEC = {"name": "t", "reference_version": "refbot-v1+icm-ref-v1+chart-v1+post-v1+short15bb", "presets": ["6max_sng_wta"],
        "blocks": 2, "rotations": 1, "seed": 3, "delta_min": 0.1, "pilot_sigma": 0.6, "alpha": 0.05, "power": 0.9}


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


def test_gate_b_cli_end_to_end_is_insufficient_on_a_small_spec(checkpoint, tmp_path):
    path, version = checkpoint
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(SPEC))
    env = {**os.environ, candidate.CHECKPOINT_ENV: str(path)}
    proc = subprocess.run([sys.executable, "-m", "referee.gate_b", "--spec", str(spec), "--candidate",
                           "stalker.rl.candidate:policy", "--out", str(tmp_path / "out")],
                          env=env, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 1, proc.stderr  # only `pass` exits 0
    res = json.loads((tmp_path / "out/gate_b.json").read_text())
    assert res["verdict"] == INSUFFICIENT
    assert res["presets"]["6max_sng_wta"]["illegal_actions"] == 0
