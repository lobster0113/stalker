"""Generate reference-bot tournament records and the typing report.

    python -m stalker.pipeline.generate --preset sng9 --n 200 --seed 1 --out runs/sng9-s1

Each game is seeded by `default_rng([seed, i])` (deal/seating) and `default_rng([seed, i, player, 1])` (bot), so a
run is reproducible from `manifest.json`. Decisions and the game result are validated while written. Hand
records are not produced yet.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

from referee.agents.reference_bot import REFERENCE_BOT_VERSION, ReferenceBot
from stalker.agents.base import Action, Agent, Event, Observation
from stalker.env.spec import from_tournament
from stalker.observe.memory import GameMemoryStore
from stalker.records.schema import (
    ActionOption, DecisionRecord, GameRecord, MemorySnapshot, PolicySource, PublicAction, RecordIds, SeatInfo,
    StackSummary, TableObservation, TournamentContext,
)
from stalker.records.store import RecordWriter, RunManifest, write_manifest
from stalker.tournament.config import TournamentConfig, load_config, load_preset, preset_names
from stalker.tournament.director import run_game
from stalker.typing.report import build_report, write_report
from stalker.typing.spots import position_label

PRESET_ALIASES = {"sng9": "9max_sng_flat", "sng6": "6max_sng_topheavy", "sng6wta": "6max_sng_wta",
                  "sng9tt": "9max_sng_503020", "mtt54": "mtt54", "mtt180": "mtt180_bbante"}
STREET_BY_BOARD = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}
MIN_PROFILE_HANDS = 10


def resolve_config(name: str) -> TournamentConfig:
    if Path(name).is_file():
        return load_config(name)
    return load_preset(PRESET_ALIASES.get(name, name))


class RecordingBot(Agent):
    """Plays like the wrapped bot and logs one DecisionRecord per decision into `sink`."""

    def __init__(self, bot: ReferenceBot, config: TournamentConfig, episode_id: str, sink: list[DecisionRecord],
                 counter: list[int]) -> None:
        self.bot, self.cfg, self.episode_id, self.sink, self.counter = bot, config, episode_id, sink, counter
        self.env_id = from_tournament(config).env_id
        self.memory = GameMemoryStore()

    def on_game_start(self, game_id: str) -> None:
        self.memory.start_game(game_id)

    def on_game_end(self, game_id: str) -> None:
        self.memory.end_game(game_id)

    def observe(self, event: Event) -> None:
        self.memory.observe(event)

    def act(self, o: Observation) -> Action:
        probs = self.bot.action_probs(o)
        total = sum(probs.values())
        la = o.legal
        space = [Action("fold")] * (la.can_fold and la.call_amount > 0) + [Action("call")]
        space += sorted((a for a in probs if a.kind == "raise"), key=lambda a: a.amount)
        space += [a for a in probs if a not in space]  # a fold/call the bot chose that is not a standard entry
        p = tuple(probs.get(a, 0.0) / total for a in space)
        choice = int(self.bot.rng.choice(len(space), p=np.array(p)))
        self.counter[0] += 1
        ev = self.bot.action_values(o)
        values = tuple(ev[a] for a in space) if ev is not None and all(a in ev for a in space) else None
        self.sink.append(self._record(o, space, p, choice, values))
        return space[choice]

    def _record(self, o: Observation, space: Sequence[Action], probs: tuple[float, ...], choice: int,
                values: tuple[float, ...] | None) -> DecisionRecord:
        cfg = self.cfg
        mem = self.memory.get(o.game_id)
        vpips = [s.vpip_hands / s.hands for p, s in mem.opponents.items()
                 if p != o.player_id and s.hands >= MIN_PROFILE_HANDS]
        snapshot = MemorySnapshot(hands_observed=mem.hands_seen,
                                  features={"opp_vpip": float(np.mean(vpips))} if vpips else {})
        seats = sorted(o.stacks)
        return DecisionRecord(
            ids=RecordIds(self.episode_id, o.game_id, o.tournament_id, o.hand_id, self.counter[0], o.player_id,
                          REFERENCE_BOT_VERSION, self.env_id),
            tournament_context=TournamentContext(
                table_size=cfg.table_size, sb=o.sb, bb=o.bb, ante_type=cfg.ante_mode if o.ante else "none",
                ante=o.ante, level=cfg.level_index_for_hand(o.hand_no), remaining=o.players_remaining,
                paid_places=o.paid_places, payout_vector=tuple(float(x) for x in cfg.payout_amounts()),
                next_level=o.next_blinds, stacks=StackSummary.of(list(o.all_stacks))),
            table_observation=TableObservation(
                seats=tuple(SeatInfo(s, o.seat_players[s], o.stacks[s], o.bets.get(s, 0), s in o.in_hand)
                            for s in seats),
                hero_seat=o.seat, button=o.button, position=position_label(seats, o.button, o.seat), pot=o.pot,
                hole_cards=tuple(o.hole_cards), board=tuple(o.board), street=STREET_BY_BOARD[len(o.board)],
                current_hand_actions=tuple(PublicAction(*a) for a in o.action_history),
                action_space=tuple(ActionOption(a.kind, a.amount) for a in space),
                legal_action_mask=(True,) * len(space)),
            session_memory_snapshot=snapshot, probs_ai0=probs, probs_ai1=None, acting_policy="ai0",
            chosen_action=choice, action_logprob=math.log(probs[choice]), action_values=values,
            policy_source=PolicySource("reference-bot", meta={"version": REFERENCE_BOT_VERSION}))


def generate(config: TournamentConfig, n: int, seed: int, out: str | Path, run_id: str | None = None) -> list[DecisionRecord]:
    """Play `n` games with reference bots, write manifest + records to `out`, return all decisions."""
    out = Path(out)
    run_id = run_id or out.name
    write_manifest(out, RunManifest.create(run_id, config, seed, REFERENCE_BOT_VERSION, meta={"n_games": str(n)}))
    payouts = config.payout_ratios()
    env_id = from_tournament(config).env_id
    all_decisions: list[DecisionRecord] = []
    with RecordWriter(out) as writer:
        for i in range(n):
            sink: list[DecisionRecord] = []
            counter = [0]
            ep = f"{run_id}-ep{i}"
            agents = [RecordingBot(ReferenceBot(np.random.default_rng([seed, i, p, 1]), payouts), config, ep, sink,
                                   counter) for p in range(config.players)]
            res = run_game(config, agents, np.random.default_rng([seed, i]), game_id=f"{run_id}-g{i}")
            for r in sink:
                writer.write(r)
            writer.write(GameRecord.from_result(res, config.prize_pool / config.players, ep, env_id))
            all_decisions += sink
    return all_decisions


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--preset", default="sng9", help=f"alias, preset name or config path; presets: {preset_names()}")
    ap.add_argument("--n", type=int, default=200, help="number of tournaments")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", required=True, help="run directory (manifest.json, records.jsonl, report.json/.md)")
    a = ap.parse_args(argv)
    if a.n < 2:
        ap.error("--n must be at least 2: the report's cluster bootstrap needs two or more games.")
    cfg = resolve_config(a.preset)
    decisions = generate(cfg, a.n, a.seed, a.out)
    report = build_report(decisions, players=cfg.players, seed=a.seed,
                          source={"preset": cfg.name, "n_games": a.n, "seed": a.seed, "policy_version": REFERENCE_BOT_VERSION})
    j, m = write_report(report, a.out)
    s = report["summary"]
    print(f"{len(decisions)} decisions, {s['cells']} cells, lessonable {s['lessonable_cells']}, "
          f"unclassified {report['unclassified']['ratio']:.1%} -> {j}, {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
