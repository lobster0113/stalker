"""Built-in candidates for `--candidate referee.gate_b.candidates:<name>` (each takes the preset config)."""
from __future__ import annotations

from referee.agents.reference_bot import factory
from stalker.agents.random_agent import RandomLegalAgent


def reference(config):
    return factory(config.payout_ratios())


def random_legal(config):
    return lambda rng: RandomLegalAgent(rng)
