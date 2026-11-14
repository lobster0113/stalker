"""ICM equity vs simulated prize money from the same mid-tournament state (#834, research rec. 2 of #827).

ICM is a model with known stack-size bias, so a tournament evaluation that only reports ICM equity would judge
policies by the model's own error. This tool measures that error in our simulator: it plays the state out to the
end `games` times and puts the per-survivor mean prize next to `icm_equity`. With symmetric agents (the default
`RandomLegalAgent`, or `--agents persona:NAME` on every seat) the gap is ICM model bias plus sampling error;
`diff_se` (= `sim_prize_sd / sqrt(games)`) and `z` (= `diff / diff_se`) tell the two apart.

Survivors are listed in ascending player_id order. They compete only for places 1..remaining, so `prize_pool` here
is `sum(payouts[:remaining])` (equal to `config.prize_pool` whenever remaining >= paid places).

    python -m stalker.tools.icm_calibration --players 6 --remaining 3 --stack-profile skewed --games 200 --seed 0
"""
from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from stalker.agents.base import Agent
from stalker.agents.persona import PersonaAgent, persona_params
from stalker.agents.random_agent import RandomLegalAgent
from stalker.core.icm import icm_equity
from stalker.tournament.config import TournamentConfig, load_preset, top_heavy
from stalker.tournament.director import run_game
from stalker.tournament.start_state import STACK_PROFILES, StartState, make_start_state

SCHEMA_VERSION = 2
DEFAULT_LEVELS_PRESET = "6max_sng_topheavy"

AgentsFactory = Callable[[TournamentConfig, np.random.Generator], Sequence[Agent]]


def random_agents(config: TournamentConfig, rng: np.random.Generator) -> list[Agent]:
    return [RandomLegalAgent(np.random.default_rng(int(s))) for s in rng.integers(2**63, size=config.players)]


def agents_factory(spec: str) -> AgentsFactory:
    """`random` or `persona:NAME` (same persona on every seat, so skill stays symmetric). Bad names fail here, before
    any game runs, with persona_params' KeyError listing the choices."""
    if spec == "random":
        return random_agents
    kind, _, name = spec.partition(":")
    if kind != "persona" or not name:
        raise ValueError(f"--agents {spec!r}: use 'random' or 'persona:NAME'.")
    params = persona_params(name)

    def personas(config: TournamentConfig, rng: np.random.Generator) -> list[Agent]:
        return [PersonaAgent(params, np.random.default_rng(int(s))) for s in rng.integers(2**63, size=config.players)]
    return personas


def calibrate(config: TournamentConfig, start_state: StartState, agents_factory: AgentsFactory | None,
              games: int, rng: np.random.Generator) -> dict:
    """Per-survivor ICM equity and simulated prize mean/sd. Same rng state -> identical output."""
    if games < 1:
        raise ValueError(f"games={games}: must be >= 1.")
    factory = agents_factory or random_agents
    players = sorted(start_state.stacks)
    stacks = [start_state.stacks[p] for p in players]
    payouts = [float(a) for a in config.payout_amounts()[:len(players)]]
    icm = icm_equity(stacks, payouts)
    prizes = np.zeros((games, len(players)))
    for g in range(games):
        agent_rng, game_rng = (np.random.default_rng(int(s)) for s in rng.integers(2**63, size=2))
        res = run_game(config, factory(config, agent_rng), game_rng, game_id=f"icm-cal-{g}", start_state=start_state)
        prizes[g] = [res.prizes[p] for p in players]
    mean = prizes.mean(axis=0)
    sd = prizes.std(axis=0, ddof=1) if games > 1 else np.zeros(len(players))
    diff = mean - np.asarray(icm, dtype=float)
    se = sd / math.sqrt(games)
    z = np.divide(diff, se, out=np.zeros_like(diff), where=se != 0)
    return {
        "schema_version": SCHEMA_VERSION,
        "config": config.to_dict(),
        "level_index": start_state.level_index,
        "players": players,
        "stacks": stacks,
        "payouts": payouts,
        "prize_pool": math.fsum(payouts),
        "icm_equity": [float(x) for x in icm],
        "sim_prize_mean": [float(x) for x in mean],
        "sim_prize_sd": [float(x) for x in sd],
        "diff": [float(x) for x in diff],
        "diff_se": [float(x) for x in se],
        "z": [float(x) for x in z],
        "games": games,
    }


def default_config(players: int) -> TournamentConfig:
    """N-player single-table SNG on the 6-max top-heavy blind schedule, top-heavy payouts to ~1/3 of the field."""
    base = load_preset(DEFAULT_LEVELS_PRESET)
    paid = max(1, min(3, players // 3))
    return TournamentConfig(name=f"icm-calibration {players}p", players=players, table_size=min(players, 10),
                            starting_stack=base.starting_stack, levels=base.levels, payouts=top_heavy(paid),
                            buy_in=base.buy_in)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--players", type=int, help="field size (default config); ignored with --preset")
    ap.add_argument("--preset", help="tournament preset name instead of the default config")
    ap.add_argument("--remaining", type=int, required=True)
    ap.add_argument("--stack-profile", choices=STACK_PROFILES, default="random")
    ap.add_argument("--level-index", type=int, default=0)
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--agents", default="random", help="random | persona:NAME (every seat)")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    try:
        factory = agents_factory(a.agents)
    except (KeyError, ValueError) as e:
        ap.exit(2, f"icm_calibration: {e.args[0]}\n")
    if a.preset:
        config = load_preset(a.preset)
    elif a.players:
        config = default_config(a.players)
    else:
        ap.error("give --players N or --preset NAME.")
    rng = np.random.default_rng(a.seed)
    ss = make_start_state(config, rng, a.remaining, a.stack_profile, a.level_index)
    out = calibrate(config, ss, factory, a.games, rng)
    out["agents"] = a.agents
    out["seed"] = a.seed
    out["stack_profile"] = a.stack_profile
    text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
