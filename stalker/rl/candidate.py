"""Gate B candidate for a trained RL checkpoint: `--candidate stalker.rl.candidate:policy` (requires `[rl]`, torch).

The checkpoint path comes from `STALKER_RL_CHECKPOINT` (Gate B calls `factory(config)` with the preset only). The
returned `rng -> PolicyAgent` factory carries `policy_version`, the exact weights being judged. Every agent shares
the loaded weights read-only; its memory and GRU state are per game (`PolicyAgent`, Gate L1/L6).
"""
from __future__ import annotations

import os
from pathlib import Path

from stalker.rl.train import PolicyAgent, load_checkpoint
from stalker.tournament.config import TournamentConfig

CHECKPOINT_ENV = "STALKER_RL_CHECKPOINT"


def policy(config: TournamentConfig, checkpoint: str | Path | None = None):
    path = checkpoint if checkpoint is not None else os.environ.get(CHECKPOINT_ENV)
    if not path:
        raise ValueError(f"no RL checkpoint: set {CHECKPOINT_ENV}=<file written by Trainer.save>.")
    if not Path(path).is_file():
        raise FileNotFoundError(f"RL checkpoint {path} not found; point {CHECKPOINT_ENV} at a Trainer.save file.")
    net, version, fractions = load_checkpoint(path)

    def make(rng):
        return PolicyAgent(net, config, rng, fractions)

    make.policy_version = version
    return make
