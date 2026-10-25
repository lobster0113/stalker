"""Multi-agent RL environment around the tournament director.

The director is callback-driven (`agent.act`), so the game runs in a worker thread and hands every
decision to `step()` through a pair of queues. Exactly one side runs at a time, so the trajectory depends
only on the injected rng and the action sequence.

Units: observations come only from `ObservationBuilder` (chips and BB). Rewards are in prize units
(`TournamentConfig.payout_amounts()`, same unit as `buy_in`): `prize - buy_in`, paid once at the end of
the game; all earlier steps carry zero reward.

Action space (index into `ActionSpec`): 0 = fold, 1 = check/call, then one raise per entry of
`raise_pot_fractions` (raise-to = own bet + call + fraction * (pot + call), clipped into the legal
range), and a last all-in entry (max raise-to). Choosing a masked action raises `ValueError`.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field

import numpy as np

from stalker.agents.base import Action, Agent, Event, Observation
from stalker.observe.builder import HeroObservation, ObservationBuilder
from stalker.observe.memory import GameMemoryStore
from stalker.tournament.config import TournamentConfig
from stalker.tournament.director import GameResult, run_game

DEFAULT_RAISE_FRACTIONS = (0.5, 1.0)
GAME_START, GAME_END = "game_start", "game_end"


def action_mask(hero: HeroObservation, raise_pot_fractions: tuple[float, ...]) -> tuple[bool, ...]:
    lg = hero.legal
    return (bool(lg["fold"]), bool(lg["call"])) + (bool(lg["raise"]),) * (len(raise_pot_fractions) + 1)


def index_to_action(hero: HeroObservation, idx: int, raise_pot_fractions: tuple[float, ...]) -> Action:
    """ActionSpec index -> engine Action; shared by the env and agents that play a trained policy outside it."""
    lg = hero.legal
    if idx == 0:
        return Action("fold")
    if idx == 1:
        return Action("call")
    lo, hi = lg["min_raise_to"], lg["max_raise_to"]
    if idx == len(raise_pot_fractions) + 2:
        return Action("raise", hi)
    frac = raise_pot_fractions[idx - 2]
    target = hero.seats[0].bet + lg["call_amount"] + frac * (hero.pot + lg["call_amount"])
    return Action("raise", int(min(hi, max(lo, round(target)))))


@dataclass(frozen=True)
class StepResult:
    player_id: int | None  # who acts next; None once the game is over
    observation: HeroObservation | None
    action_mask: tuple[bool, ...]  # over ActionSpec indices; all False when done
    rewards: tuple[float, ...]  # by player_id; zeros until the game ends
    done: bool
    events: tuple[str, ...] = ()  # game boundary markers since the previous result
    result: GameResult | None = None


class _Abort(BaseException):
    """Unwinds the game thread when the env is reset or closed."""


class _SeatAgent(Agent):
    def __init__(self, env: "TournamentEnv", player_id: int) -> None:
        self.env, self.pid = env, player_id
        self.memory = GameMemoryStore()

    def on_game_start(self, game_id: str) -> None:
        self.memory.start_game(game_id)

    def observe(self, event: Event) -> None:
        self.memory.observe(event)

    def on_game_end(self, game_id: str) -> None:
        self.memory.end_game(game_id)

    def act(self, observation: Observation) -> Action:
        hero = self.env._builder.build(observation, self.memory.get(observation.game_id))
        return self.env._ask(self.pid, hero)


class TournamentEnv:
    def __init__(self, config: TournamentConfig, raise_pot_fractions: tuple[float, ...] = DEFAULT_RAISE_FRACTIONS) -> None:
        if any(f <= 0 for f in raise_pot_fractions):
            raise ValueError("raise_pot_fractions must be positive.")
        self.config = config
        self.raise_pot_fractions = tuple(raise_pot_fractions)
        self.n_actions = 2 + len(self.raise_pot_fractions) + 1
        self._builder = ObservationBuilder(config)
        self._thread: threading.Thread | None = None
        self._to_env: queue.Queue = queue.Queue()
        self._to_game: queue.Queue = queue.Queue()
        self._events: list[str] = []
        self._pending: tuple[int, HeroObservation] | None = None

    # ---- public API ----
    def reset(self, rng: np.random.Generator, game_id: str = "game-0") -> StepResult:
        """Start a new tournament; `rng` drives every random draw of the game."""
        self.close()
        self._to_env, self._to_game = queue.Queue(), queue.Queue()
        self._events, self._pending = [], None
        agents = [_SeatAgent(self, p) for p in range(self.config.players)]

        def observer(e: Event) -> None:
            if e.type == "START_GAME":
                self._events.append(GAME_START)
            elif e.type == "END_GAME":
                self._events.append(GAME_END)

        def run() -> None:
            try:
                self._to_env.put(("done", run_game(self.config, agents, rng, observer, game_id)))
            except _Abort:
                pass
            except BaseException as exc:  # surfaced to the caller of step()/reset()
                self._to_env.put(("error", exc))

        self._thread = threading.Thread(target=run, daemon=True, name="stalker-env")
        self._thread.start()
        return self._next()

    def step(self, action: int) -> StepResult:
        if self._pending is None:
            raise RuntimeError("game is over or not started; call reset().")
        pid, hero = self._pending
        mask = self.action_mask(hero)
        if not 0 <= action < self.n_actions or not mask[action]:
            raise ValueError(f"action {action} is not legal for player {pid}; legal indices: "
                             f"{[i for i, m in enumerate(mask) if m]}.")
        self._pending = None
        self._to_game.put(self._to_action(hero, action))
        return self._next()

    def close(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._to_game.put(_Abort())
            self._thread.join()
        self._thread, self._pending = None, None

    def action_mask(self, hero: HeroObservation) -> tuple[bool, ...]:
        return action_mask(hero, self.raise_pot_fractions)

    # ---- internals ----
    def _to_action(self, hero: HeroObservation, idx: int) -> Action:
        return index_to_action(hero, idx, self.raise_pot_fractions)

    def _ask(self, pid: int, hero: HeroObservation) -> Action:
        self._to_env.put(("decision", pid, hero))
        reply = self._to_game.get()
        if isinstance(reply, _Abort):
            raise reply
        return reply

    def _next(self) -> StepResult:
        msg = self._to_env.get()
        events, self._events = tuple(self._events), []
        if msg[0] == "error":
            self._thread = None
            raise msg[1]
        if msg[0] == "done":
            res: GameResult = msg[1]
            self._thread.join()
            rewards = tuple(p - self.config.buy_in for p in res.prizes)
            return StepResult(None, None, (False,) * self.n_actions, rewards, True, events, res)
        _, pid, hero = msg
        self._pending = (pid, hero)
        return StepResult(pid, hero, self.action_mask(hero), (0.0,) * self.config.players, False, events)
