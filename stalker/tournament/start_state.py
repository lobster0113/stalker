"""Mid-tournament starting states and the tournament-stage classifier.

Conventions:
- `StartState.stacks` maps the surviving player_ids to their chips; every other player is already eliminated
  and takes places `remaining+1 .. players` in ascending player_id order (they never sit down).
- `level_index` selects the blind level in force at the first hand; the level clock starts at that level's start.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from stalker.tournament.config import TournamentConfig

STAGES = ("early", "middle", "bubble_near", "in_the_money", "final_table")
STACK_PROFILES = ("even", "random", "skewed")
_ALPHA = {"random": 4.0, "skewed": 0.7}  # Dirichlet concentration: low = a few big stacks, many shorts


@dataclass(frozen=True)
class StartState:
    stacks: dict[int, int]  # surviving player_id -> chips
    eliminated: int  # players already out (they hold places remaining+1..players)
    level_index: int
    button: int | None = None  # seat of the first table's button; None = drawn from the game rng

    @property
    def remaining(self) -> int:
        return len(self.stacks)


def validate_start_state(config: TournamentConfig, ss: StartState) -> None:
    """Raise ValueError (with the fix) unless `ss` is a legal state of `config`."""
    if not ss.stacks:
        raise ValueError("start_state has no surviving players.")
    if not set(ss.stacks) <= set(range(config.players)):
        raise ValueError(f"start_state player ids must be in 0..{config.players - 1}.")
    if any(isinstance(c, bool) or not isinstance(c, int) or c <= 0 for c in ss.stacks.values()):
        raise ValueError("start_state stacks must be positive integers.")
    total = config.starting_stack * config.players
    if sum(ss.stacks.values()) != total:
        raise ValueError(f"start_state stacks sum to {sum(ss.stacks.values())}, expected {total} "
                         "(starting_stack * players).")
    if ss.eliminated != config.players - ss.remaining:
        raise ValueError(f"eliminated={ss.eliminated} but players - remaining = {config.players - ss.remaining}.")
    if not 0 <= ss.level_index < len(config.levels):
        raise ValueError(f"level_index={ss.level_index}: must be in 0..{len(config.levels) - 1}.")
    if ss.button is not None and not 0 <= ss.button < config.table_size:
        raise ValueError(f"button={ss.button}: must be a seat in 0..{config.table_size - 1}.")


def level_start(config: TournamentConfig, level_index: int) -> int:
    """Time (hands played, or minutes elapsed) at which `level_index` begins."""
    return sum(lv.length for lv in config.levels[:level_index])


def make_start_state(config: TournamentConfig, rng: np.random.Generator, remaining: int,
                     stack_profile: str = "random", level_index: int = 0) -> StartState:
    """Draw survivors and a chip split of the whole field's chips among them. Same seed -> same state."""
    if stack_profile not in STACK_PROFILES:
        raise ValueError(f"stack_profile={stack_profile!r}: must be one of {STACK_PROFILES}.")
    if not 1 <= remaining <= config.players:
        raise ValueError(f"remaining={remaining}: must be in 1..{config.players}.")
    total = config.starting_stack * config.players
    if total < remaining:
        raise ValueError("fewer chips than survivors.")
    survivors = sorted(int(p) for p in rng.choice(config.players, size=remaining, replace=False))
    spare = total - remaining  # every survivor keeps at least one chip
    if stack_profile == "even":
        extra = [spare // remaining + (1 if i < spare % remaining else 0) for i in range(remaining)]
    else:
        w = rng.dirichlet([_ALPHA[stack_profile]] * remaining)
        extra = [int(x) for x in np.floor(w * spare)]
        extra[int(np.argmax(w))] += spare - sum(extra)
    button = int(rng.integers(config.table_size))
    ss = StartState({p: 1 + e for p, e in zip(survivors, extra)}, config.players - remaining, level_index, button)
    validate_start_state(config, ss)
    return ss


def tournament_stage(remaining: int, paid_places: int, table_size: int, players: int) -> str:
    """Stage of a tournament with `remaining` of `players` left. Checked in this order:
    in_the_money: remaining <= paid_places;
    bubble_near: remaining <= paid_places + max(1, ceil(paid_places / 2));
    final_table: remaining <= table_size;
    early: at least 75% of the field left; middle: otherwise.
    """
    if remaining < 1 or remaining > players or paid_places < 1 or table_size < 2:
        raise ValueError(f"bad arguments: remaining={remaining} paid_places={paid_places} "
                         f"table_size={table_size} players={players}.")
    if remaining <= paid_places:
        return "in_the_money"
    if remaining <= paid_places + max(1, -(-paid_places // 2)):
        return "bubble_near"
    if remaining <= table_size:
        return "final_table"
    return "early" if remaining * 4 >= players * 3 else "middle"
