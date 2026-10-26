"""Issue #78 experiment: does an RL opponent pool (reference-bot seats, past checkpoints) help against the reference bot?

    python scripts/rl_opponent_pool.py SETTING --seed S --budget 600 --eval-games 400 --out DIR

Trains one `TrainConfig` setting for a fixed wall-clock CPU budget (one torch thread, so settings run side by side
get the same budget), then plays the policy in one rotating seat against 5 reference bots v1 and against 5 random
bots. Numbers are local and reference-only (CHARTER: only CI results count).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import time
from pathlib import Path

import numpy as np
import torch

from referee.agents.reference_bot import ReferenceBot
from stalker.agents.base import Action, Agent
from stalker.agents.random_agent import RandomLegalAgent
from stalker.rl.train import PolicyAgent, TrainConfig, Trainer
from stalker.tournament.config import BlindLevel, TournamentConfig
from stalker.tournament.director import run_game

BASE = TrainConfig(seed=0, games_per_iter=8, epochs=2)
SETTINGS = {
    "random": dataclasses.replace(BASE, random_seats=4),
    "reference": dataclasses.replace(BASE, random_seats=2, reference_seats=2),
    "reference_past": dataclasses.replace(BASE, random_seats=2, reference_seats=1, past_checkpoints=5,
                                          past_checkpoint_p=0.5),
    # no random seats: random bots reward check/fold, which is all the first three settings learned (see the record)
    "reference4": dataclasses.replace(BASE, reference_seats=4),
    "reference3_past": dataclasses.replace(BASE, reference_seats=3, past_checkpoints=5, past_checkpoint_p=0.5),
}


def hyper_sng() -> TournamentConfig:  # same table as the slow smoke test (tests/test_rl_env.py)
    return TournamentConfig(
        name="6max hyper SNG", players=6, table_size=6, starting_stack=500,
        levels=(BlindLevel(10, 20, 0, 3), BlindLevel(25, 50, 0, 3), BlindLevel(50, 100, 0, 3),
                BlindLevel(100, 200, 0, 3), BlindLevel(200, 400, 0, 3), BlindLevel(500, 1000, 0, 3)),
        payouts=(0.5, 0.3, 0.2), buy_in=100)


class CheckFold(Agent):
    """Baseline: check when free, fold to any bet. A trained policy that matches its ROI learned nothing more."""

    def act(self, observation):
        la = observation.legal
        return Action("fold") if la.call_amount > 0 and la.can_fold else Action("call")


class _Probe(PolicyAgent):
    """Counts the chosen action kind and how often the policy is (almost) deterministic."""

    def __init__(self, *args, tally: dict, **kw):
        super().__init__(*args, **kw)
        self.tally = tally

    def act(self, observation):
        hero, out = self._forward(observation)
        probs = out.probs[0].double().numpy()
        action = super().act(observation)  # recomputes the same forward pass and advances the GRU
        kind = "allin" if action.kind == "raise" and action.amount == hero.legal["max_raise_to"] else action.kind
        self.tally[kind] = self.tally.get(kind, 0) + 1
        self.tally["decisions"] = self.tally.get("decisions", 0) + 1
        self.tally["p_max>0.99"] = self.tally.get("p_max>0.99", 0) + int(probs.max() > 0.99)
        return action


def roi(make_hero, cfg: TournamentConfig, opponent: str, games: int, seed: int) -> tuple[float, float]:
    """Mean ROI of `make_hero(rng)` in one rotating seat and its standard error (per-game). Every setting sees the
    same deals and opponent seeds, so differences between settings are paired."""
    out = []
    for g in range(games):
        seat = g % cfg.players
        if opponent == "reference":
            agents = [ReferenceBot(np.random.default_rng([seed, g, i]), cfg.payout_ratios()) for i in range(cfg.players)]
        else:
            agents = [RandomLegalAgent(np.random.default_rng([seed, g, i])) for i in range(cfg.players)]
        agents[seat] = make_hero(np.random.default_rng([seed, g]))
        res = run_game(cfg, agents, np.random.default_rng([seed, g, 99]), game_id=f"eval-{g}")
        out.append((res.prizes[seat] - cfg.buy_in) / cfg.buy_in)
    a = np.array(out)
    return float(a.mean()), float(a.std(ddof=1) / np.sqrt(len(a)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("setting", choices=sorted(SETTINGS) + ["checkfold"], help="checkfold = baseline, no training")
    ap.add_argument("--budget", type=float, default=600.0, help="training wall-clock seconds")
    ap.add_argument("--eval-games", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0, help="TrainConfig.seed")
    ap.add_argument("--out", type=Path, default=Path("."))
    args = ap.parse_args()
    torch.set_num_threads(1)
    cfg = hyper_sng()
    if args.setting == "checkfold":
        row = {"setting": "checkfold", "eval_games": args.eval_games}
        for opp in ("reference", "random"):
            m, se = roi(lambda rng: CheckFold(), cfg, opp, args.eval_games, seed=7)
            row[f"roi_vs_{opp}"], row[f"se_vs_{opp}"] = round(m, 4), round(se, 4)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "checkfold.json").write_text(json.dumps(row, indent=1))
        print(json.dumps(row))
        return
    cfg_t = dataclasses.replace(SETTINGS[args.setting], seed=args.seed)
    tr = Trainer(cfg, cfg_t)
    start = time.monotonic()
    while time.monotonic() - start < args.budget:
        tr.train_step()
    train_s = time.monotonic() - start
    row = {"setting": args.setting, "train_config": dataclasses.asdict(cfg_t), "budget_s": args.budget,
           "train_s": round(train_s, 1), "iterations": tr.iteration, "games": tr.games_played,
           "policy_version": tr.policy_version, "eval_games": args.eval_games}
    for opp in ("reference", "random"):
        tally: dict = {}
        m, se = roi(lambda rng: _Probe(tr.policy, cfg, rng, cfg_t.raise_pot_fractions, tally=tally),
                    cfg, opp, args.eval_games, seed=7)
        row[f"roi_vs_{opp}"], row[f"se_vs_{opp}"] = round(m, 4), round(se, 4)
        n = tally.pop("decisions", 0)
        row[f"actions_vs_{opp}"] = {k: round(v / max(n, 1), 3) for k, v in sorted(tally.items())}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{args.setting}-s{args.seed}.json").write_text(json.dumps(row, indent=1))
    tr.save(args.out / f"{args.setting}-s{args.seed}.pt")
    print(json.dumps(row))


if __name__ == "__main__":
    main()
