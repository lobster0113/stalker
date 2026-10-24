"""Gate R suite: seeded tournaments with legal-random bots, every event checked by `checks.check_game`."""
from __future__ import annotations

import dataclasses

import numpy as np

from referee.gate_r.checks import Tally, check_game
from stalker.agents.base import Action, Agent, Observation
from stalker.agents.random_agent import RandomLegalAgent
from stalker.tournament.config import load_preset, preset_names
from stalker.tournament.director import run_game

SLOW_PRESETS = ("mtt180_bbante",)
SLOW_SEEDS = 2  # a 180-player game checks ~100x the hands of a sit-and-go
FAST_LEVEL_LENGTH = 2  # hands per level in the "fast" variant: reaches ante levels and short-stack postings


class CallingStation(Agent):
    """Rarely folds or raises: many multiway showdowns, split pots and side pots."""

    def __init__(self, rng: np.random.Generator) -> None:
        self.rng = rng

    def act(self, obs: Observation) -> Action:
        la, r = obs.legal, self.rng.random()
        if la.can_fold and la.call_amount > 0 and r < 0.1:
            return Action("fold")
        if la.min_raise_to is not None and r > 0.92:
            return Action("raise", la.max_raise_to if r > 0.99 else la.min_raise_to)
        return Action("call")


BOTS = {"random": RandomLegalAgent, "station": CallingStation}


def variants(preset: str):
    cfg = load_preset(preset)
    yield preset, cfg
    fast = tuple(dataclasses.replace(lv, length=FAST_LEVEL_LENGTH) for lv in cfg.levels)
    yield f"{preset}/fast", dataclasses.replace(cfg, levels=fast)


def run_suite(seeds: int = 5, full: bool = False, presets=None) -> Tally:
    tally = Tally()
    for preset in presets or preset_names():
        if preset in SLOW_PRESETS and not full and presets is None:
            continue
        for name, cfg in variants(preset):
            for bot, cls in BOTS.items():
                for seed in range(min(seeds, SLOW_SEEDS) if preset in SLOW_PRESETS else seeds):
                    events: list = []
                    agents = [cls(np.random.default_rng([seed, i])) for i in range(cfg.players)]
                    res = run_game(cfg, agents, np.random.default_rng(seed), observer=events.append)
                    check_game(cfg, events, res, tally, f"{name} {bot} seed {seed}")
    return tally
