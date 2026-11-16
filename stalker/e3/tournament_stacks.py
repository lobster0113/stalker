"""Tournament training stacks for E3 (#898, ADR 0027 decisions 4-5).

A mid-tournament state of a preset (`make_start_state`: who survives and their chips) becomes the table an E3
hand is dealt with: each survivor's chips in E3 BB units at the blind of the chosen level.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from stalker.e3 import game as G
from stalker.tournament.config import TournamentConfig, load_preset
from stalker.tournament.start_state import make_start_state

_load = lru_cache(maxsize=None)(load_preset)   # a training run draws one table per hand; read the preset once


def sample_tournament_stacks(rng: np.random.Generator, preset: str | TournamentConfig, remaining: int,
                             level_index: int, profile: str, min_chips: int = 1) -> tuple[int, ...]:
    """E3 starting stacks (integer chips, `game.BB` per big blind) of `remaining` survivors of `preset`.

    chips * G.BB / (the level's bb), rounded, at least `min_chips`. The training table passes `2 * G.BB` because
    `game.deal` refuses shorter stacks (a seat below 2BB is not a decision the E3 tree models). Same seed, same
    tuple. The seats come in survivor id order, which carries no information (the draw is exchangeable)."""
    config = _load(preset) if isinstance(preset, str) else preset
    ss = make_start_state(config, rng, remaining, profile, level_index)
    bb = config.levels[level_index].bb
    return tuple(max(min_chips, int(round(c * G.BB / bb))) for _, c in sorted(ss.stacks.items()))
