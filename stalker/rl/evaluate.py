"""RL evaluation with a check/fold baseline on the same deals (#88). Requires the optional `[rl]` extra (torch).

The policy plays one seat (rotated per game) against fixed opponents; `CheckFoldAgent` then plays the same seat with
the same deals and opponent seeds, so the two ROIs are paired. ROI vs random bots alone has no discriminating power:
check/fold earns about +0.75 there (#78). The policy's action distribution exposes a check/fold collapse directly.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Callable

import numpy as np

from referee.agents.reference_bot import ReferenceBot
from stalker.agents.base import Action, Agent, Observation
from stalker.agents.check_fold import CheckFoldAgent
from stalker.agents.random_agent import RandomLegalAgent
from stalker.rl.env import DEFAULT_RAISE_FRACTIONS
from stalker.rl.policy import Policy
from stalker.rl.train import PolicyAgent
from stalker.tournament.config import TournamentConfig
from stalker.tournament.director import run_game

OPPONENTS = ("random", "reference")
ACTION_KINDS = ("fold", "check_call", "raise", "allin")


@dataclass(frozen=True)
class EvalResult:
    opponent: str
    games: int
    roi: float  # mean (prize - buy_in) / buy_in of the policy seat
    roi_se: float  # per-game standard error
    baseline_roi: float  # CheckFoldAgent in the same seat, same deals
    baseline_se: float
    decisions: int
    actions: dict[str, float]  # share of the policy's decisions per ACTION_KINDS
    facing_bet: int  # decisions where folding was legal (call_amount > 0)
    fold_rate: float  # folds / facing_bet. Over all decisions a pure check/fold policy folds only ~0.7, since it
    # checks whenever that is free, so the share of all decisions cannot tell it apart from a passive policy.

    def as_dict(self) -> dict:
        return asdict(self)


class _Tally(PolicyAgent):
    def __init__(self, *args, counts: Counter, **kw) -> None:
        super().__init__(*args, **kw)
        self.counts = counts

    def act(self, observation: Observation) -> Action:
        action = super().act(observation)
        if observation.legal.call_amount > 0 and observation.legal.can_fold:
            self.counts["facing_bet"] += 1
            self.counts["facing_bet_fold"] += action.kind == "fold"
        if action.kind == "raise":
            kind = "allin" if action.amount == observation.legal.max_raise_to else "raise"
        else:
            kind = "check_call" if action.kind == "call" else "fold"
        self.counts[kind] += 1
        return action


def _opponents(opponent: str, cfg: TournamentConfig, seed: int, g: int) -> list[Agent]:
    if opponent == "reference":
        return [ReferenceBot(np.random.default_rng([seed, g, i]), cfg.payout_ratios()) for i in range(cfg.players)]
    return [RandomLegalAgent(np.random.default_rng([seed, g, i])) for i in range(cfg.players)]


def seat_roi(make_hero: Callable[[np.random.Generator], Agent], cfg: TournamentConfig, opponent: str, games: int,
             seed: int) -> tuple[float, float]:
    """Mean ROI of `make_hero(rng)` in one rotating seat and its per-game standard error. Deals and opponent seeds
    depend only on (`seed`, game index), so any two heroes evaluated with the same seed are paired."""
    if opponent not in OPPONENTS:
        raise ValueError(f"opponent must be one of {OPPONENTS}, got {opponent!r}.")
    if games < 2:
        raise ValueError("games must be at least 2 to estimate a standard error.")
    out = []
    for g in range(games):
        seat = g % cfg.players
        agents = _opponents(opponent, cfg, seed, g)
        agents[seat] = make_hero(np.random.default_rng([seed, g]))
        res = run_game(cfg, agents, np.random.default_rng([seed, g, 99]), game_id=f"eval-{g}")
        out.append((res.prizes[seat] - cfg.buy_in) / cfg.buy_in)
    a = np.array(out)
    return float(a.mean()), float(a.std(ddof=1) / np.sqrt(len(a)))


def evaluate(policy: Policy, cfg: TournamentConfig, games: int, seed: int, opponent: str = "random",
             raise_pot_fractions: tuple[float, ...] = DEFAULT_RAISE_FRACTIONS) -> EvalResult:
    counts: Counter = Counter()
    roi, se = seat_roi(lambda rng: _Tally(policy, cfg, rng, raise_pot_fractions, counts=counts),
                       cfg, opponent, games, seed)
    base, base_se = seat_roi(lambda rng: CheckFoldAgent(), cfg, opponent, games, seed)
    n = sum(counts[k] for k in ACTION_KINDS)
    actions = {k: counts[k] / n if n else 0.0 for k in ACTION_KINDS}
    facing = counts["facing_bet"]
    fold_rate = counts["facing_bet_fold"] / facing if facing else 0.0
    return EvalResult(opponent, games, roi, se, base, base_se, n, actions, facing, fold_rate)
