"""Duplicate tournament evaluation of a candidate agent type against a baseline type.

Scheme (one *block* = one bootstrap cluster):
- A block has one game seed. With the same seed the director draws the same seating permutation
  and (until the games diverge) the same decks, so the games below share their luck.
- player_ids are split by a contiguous mask: ids 0..ceil(n/2)-1 play the candidate (A), the rest
  the baseline (B). For each of `rotations` cyclic shifts of that mask (shift r moves it by r ids),
  the block plays the shifted mask and its complement (A and B swap every position). A contiguous
  mask (not alternating) is used so that every allowed shift gives new masks: with n even a shift
  by n/2 equals the complement of shift 0, so rotations <= n/2; with n odd rotations <= n.
- Each game's diff = mean ROI of A players - mean ROI of B players; the block diff is the mean
  over its 2 * rotations games. ROI = (prize - entry) / entry with entry = prize_pool / players.
- Agent rngs are keyed by (seed, block, game, player_id), so two instances of the same agent
  type are different players and an A/A run is not trivially zero.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Callable

import numpy as np

from referee.stats import CI, bootstrap_ci
from stalker.agents.base import Agent
from stalker.tournament.config import TournamentConfig
from stalker.tournament.director import run_game

SCHEMA_VERSION = 1
SEED_POLICY = ("block b: game rng = default_rng([seed, b]) shared by all games of the block; "
               "agent rng = default_rng([seed, b, game, player_id, 1]); bootstrap rng = default_rng([seed, 2])")

AgentFactory = Callable[[np.random.Generator], Agent]


@dataclass(frozen=True)
class EvalResult:
    config: dict
    candidate: str
    baseline: str
    seed: int
    seed_policy: str
    reference_version: str | None
    blocks: int
    rotations: int
    games: int
    block_diffs: list[float]
    roi_candidate: float
    roi_baseline: float
    ci: CI
    illegal_actions: int
    schema_version: int = field(default=SCHEMA_VERSION)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def max_rotations(players: int) -> int:
    return players // 2 if players % 2 == 0 else players


def _masks(players: int, rotations: int) -> list[list[bool]]:
    if not 1 <= rotations <= max_rotations(players):
        raise ValueError(f"rotations={rotations}: must be in 1..{max_rotations(players)} for {players} players "
                         "(more shifts repeat earlier masks).")
    base = [p < (players + 1) // 2 for p in range(players)]
    out = []
    for r in range(rotations):
        m = base[-r:] + base[:-r] if r else list(base)
        out += [m, [not v for v in m]]
    return out


def evaluate(config: TournamentConfig, candidate: AgentFactory, baseline: AgentFactory, *,
             blocks: int, seed: int, rotations: int = 1, candidate_name: str = "candidate",
             baseline_name: str = "baseline", reference_version: str | None = None,
             level: float = 0.95) -> EvalResult:
    """Play `blocks` duplicate blocks and return the candidate-minus-baseline ROI diff with its CI."""
    if blocks < 2:
        raise ValueError(f"blocks={blocks}: need at least 2 blocks (clusters) for a CI.")
    entry = config.prize_pool / config.players
    if entry <= 0:
        raise ValueError("prize pool is 0, ROI is undefined; set buy_in or use payout_mode='amount'.")
    masks = _masks(config.players, rotations)
    block_diffs, roi_a, roi_b, illegal = [], [], [], 0
    for b in range(blocks):
        game_diffs = []
        for g, mask in enumerate(masks):
            agents = [(candidate if mask[p] else baseline)(np.random.default_rng([seed, b, g, p, 1]))
                      for p in range(config.players)]
            res = run_game(config, agents, np.random.default_rng([seed, b]), game_id=f"eval-{seed}-{b}-{g}")
            illegal += res.illegal_actions
            roi = [(prize - entry) / entry for prize in res.prizes]
            a = float(np.mean([r for r, m in zip(roi, mask) if m]))
            o = float(np.mean([r for r, m in zip(roi, mask) if not m]))
            roi_a.append(a)
            roi_b.append(o)
            game_diffs.append(a - o)
        block_diffs.append(float(np.mean(game_diffs)))
    ci = bootstrap_ci(block_diffs, level=level, rng=np.random.default_rng([seed, 2]))
    return EvalResult(config.to_dict(), candidate_name, baseline_name, seed, SEED_POLICY, reference_version,
                      blocks, rotations, blocks * len(masks), block_diffs, float(np.mean(roi_a)),
                      float(np.mean(roi_b)), ci, illegal)
