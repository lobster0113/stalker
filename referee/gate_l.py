"""Gate L: information-leak and memory-boundary checks (GATES.md Gate L). `python -m referee.gate_l`.

Two kinds of checks:
- agent checks (L1, L2, L5-agent) take any `Agent` factory and probe its policy through `policy_of`;
  an agent may expose `action_probs(obs) -> {action: prob}`, otherwise a deep copy of it is asked to `act`
  (so equal state means equal action) and the answer is treated as a point mass.
- pipeline checks (L3, L4, L5-memory) test `ObservationBuilder` / `GameMemoryStore`, the only door to an AI policy.
L2 needs an agent that declares `uses_memory = True`; L6 needs a learner. Both need the optional `[rl]` extra (torch):
without it they report `skipped`, and the CI `rl` job (STALKER_REQUIRE_TORCH=1) runs them for real.
"""
from __future__ import annotations

import copy
import dataclasses
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from referee.agents.reference_bot import ReferenceBot
from stalker.agents.base import Action, Agent, Event, Observation
from stalker.agents.random_agent import RandomLegalAgent
from stalker.core.cards import N_CARDS, card_str
from stalker.env.contract import PrivateWorldState, TeacherContext, decision_context
from stalker.env.teacher import opp_range_label
from stalker.observe.builder import HeroObservation, ObservationBuilder
from stalker.observe.memory import GameMemoryStore
from stalker.tournament.config import TournamentConfig, load_preset
from stalker.tournament.director import run_game

CARD_INDEX = {card_str(i): i for i in range(52)}
CARD = re.compile(r"^[2-9TJQKA][cdhs]$")
FORBIDDEN_KEYS = ("seed", "deck", "rng", "generator")
L1_PRESETS = ("6max_sng_wta", "9max_sng_flat")
L1_LOG_SEEDS = (11, 12, 13)  # distinct A-game logs shown before the B game
L3_PRESETS = ("6max_sng_wta", "9max_sng_flat", "mtt54")  # mtt54 has several tables: other-table logs must not leak
SKIP_L2 = "L2 skipped: agent does not declare uses_memory=True. Set it on an agent that reads earlier hands to enable L2."
SKIP_TORCH = ("L2/L6 skipped: torch is not installed, so the RL PolicyAgent and trainer cannot run. "
              'Install it (python -m pip install -e ".[dev,rl]") to check them.')
RL_AGENT = "rl_policy_v0"
L6_GAMES = 2
L7_WORLDS = 50
L7_DECISIONS = 6
L7_SEED = 71


@dataclass
class Report:
    """item -> [passed, total]; `failures` hold actionable messages, `skipped` the activation conditions."""

    counts: dict[str, list[int]] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def check(self, item: str, ok: bool, msg: str) -> None:
        c = self.counts.setdefault(item, [0, 0])
        c[1] += 1
        if ok:
            c[0] += 1
        else:
            self.failures.append(f"{item}: {msg}")

    @property
    def ok(self) -> bool:
        return not self.failures


class _Tap(RandomLegalAgent):
    """Random bot that records the events it receives and each decision with the events seen before it."""

    def __init__(self, rng: np.random.Generator) -> None:
        super().__init__(rng)
        self.events: list[Event] = []
        self.decisions: list[tuple[Observation, int]] = []  # (observation, number of events seen so far)

    def observe(self, event: Event) -> None:
        self.events.append(event)

    def act(self, observation: Observation):
        self.decisions.append((observation, len(self.events)))
        return super().act(observation)


def record_game(cfg: TournamentConfig, seed: int, game_id: str) -> _Tap:
    """Play a random game; return the tap of the player who survived longest (most decisions)."""
    taps = [_Tap(np.random.default_rng([seed, i])) for i in range(cfg.players)]
    run_game(cfg, taps, np.random.default_rng(seed), game_id=game_id)
    return max(taps, key=lambda t: len(t.decisions))


def policy_of(agent: Agent, obs: Observation) -> tuple:
    if hasattr(agent, "action_probs"):
        return tuple(sorted((str(k), float(v)) for k, v in agent.action_probs(obs).items()))
    a = copy.deepcopy(agent).act(obs)
    return (((a.kind, a.amount), 1.0),)


def _feed(agent: Agent, game_id: str, events: list[Event]) -> None:
    agent.on_game_start(game_id)
    for e in events:
        agent.observe(e)


def check_l1(make_agent: Callable[[], Agent], report: Report, presets=L1_PRESETS) -> None:
    """Same first B decision, different A logs seen earlier: the action distribution must not move."""
    for preset in presets:
        cfg = load_preset(preset)
        b = record_game(cfg, 99, "gate-l-B")
        obs_b, n_b = b.decisions[0]
        b_events = b.events[:n_b]
        logs = [None] + [record_game(cfg, s, "gate-l-A").events for s in L1_LOG_SEEDS]
        probs = []
        for log in logs:
            agent = make_agent()
            if log is not None:
                _feed(agent, "gate-l-A", log)
                agent.on_game_end("gate-l-A")
            _feed(agent, "gate-l-B", b_events)
            probs.append(policy_of(agent, obs_b))
        same = all(p == probs[0] for p in probs)
        report.check("L1", same, f"{preset}: first decision of game B depends on game A's log. "
                     "Keep opponent stats per game_id and drop them in on_game_end; no module-level or class-level state.")


def _flip_earlier_actions(events: list[Event], hand_id: int) -> list[Event]:
    out = []
    for e in events:
        if e.type == "ACTION" and e.hand_id is not None and e.hand_id < hand_id:
            d = dict(e.data, action="raise", amount=max(e.data["amount"], 1))
            e = dataclasses.replace(e, data=d)
        out.append(e)
    return out


def check_l2(make_agent: Callable[[], Agent], report: Report, preset: str = "6max_sng_wta") -> None:
    """An agent that claims to use memory must react when earlier public hands of the same game change."""
    if not getattr(make_agent(), "uses_memory", False):
        report.skipped.append(SKIP_L2)
        return
    cfg = load_preset(preset)
    tap = record_game(cfg, 7, "gate-l-L2")
    obs, n = tap.decisions[-1]
    if obs.hand_id <= 1:
        report.check("L2", False, f"{preset}: scenario has no earlier hand; pick a longer preset.")
        return
    base = make_agent()
    _feed(base, obs.game_id, tap.events[:n])
    alt = make_agent()
    _feed(alt, obs.game_id, _flip_earlier_actions(tap.events[:n], obs.hand_id))
    report.check("L2", policy_of(base, obs) != policy_of(alt, obs),
                 "agent declares uses_memory=True but its policy ignored changed earlier hands. "
                 "Feed observe() events into the memory and make the decision depend on it.")


def scan_leaks(ho: HeroObservation, allowed_cards: set[str]) -> list[str]:
    """Return a message per leaked card or forbidden field in a HeroObservation (recursive)."""
    bad = []
    for path, leaf in _leaves(ho):
        if isinstance(leaf, str) and CARD.match(leaf) and leaf not in allowed_cards:
            bad.append(f"card {leaf} at {path} is neither own hole card, board nor shown down")
        if isinstance(leaf, (np.random.Generator, np.random.RandomState, bytes)):
            bad.append(f"random/raw object at {path}")
        if any(k in path.lower() for k in FORBIDDEN_KEYS):
            bad.append(f"forbidden field name in {path}")
    return bad


def _leaves(x, path=""):
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        for f in dataclasses.fields(x):
            yield from _leaves(getattr(x, f.name), f"{path}.{f.name}")
    elif isinstance(x, dict):
        for k, v in x.items():
            yield from _leaves(k, f"{path}[key]")
            yield from _leaves(v, f"{path}[{k}]")
    elif isinstance(x, (list, tuple)):
        for i, v in enumerate(x):
            yield from _leaves(v, f"{path}[{i}]")
    else:
        yield path, x


class _PipelineAgent(_Tap):
    """Tap that feeds its own GameMemoryStore and builds a HeroObservation per decision."""

    def __init__(self, rng: np.random.Generator, cfg: TournamentConfig) -> None:
        super().__init__(rng)
        self.builder, self.store = ObservationBuilder(cfg), GameMemoryStore()
        self.built: list[tuple[HeroObservation, Observation, set[str], int]] = []
        self.public: set[str] = set()

    def on_game_start(self, game_id: str) -> None:
        self.store.start_game(game_id)

    def observe(self, event: Event) -> None:
        super().observe(event)
        self.store.observe(event)
        if event.type == "SHOWDOWN":
            self.public |= {c for cs in event.data["hands"].values() for c in cs} | set(event.data["board"])

    def act(self, observation: Observation):
        mem = self.store.get(observation.game_id)
        self.built.append((self.builder.build(observation, mem), observation, set(self.public), len(self.events)))
        return super().act(observation)

    def on_game_end(self, game_id: str) -> None:
        self.store.end_game(game_id)


def _pipeline_game(cfg: TournamentConfig, seed: int, game_id: str) -> list[_PipelineAgent]:
    agents = [_PipelineAgent(np.random.default_rng([seed, i]), cfg) for i in range(cfg.players)]
    run_game(cfg, agents, np.random.default_rng(seed), game_id=game_id)
    return agents


def foreign_table_events(events: list[Event], player_id: int) -> list[str]:
    """Hand events are legitimate only for hands whose NEW_HAND seated this player (tables change by rebalancing)."""
    seated = {e.hand_id for e in events if e.type == "NEW_HAND" and player_id in e.data["seat_players"].values()}
    return [f"event {e.type} of hand {e.hand_id} (table {e.table_id}) reached player {player_id} who was not seated"
            for e in events if e.hand_id is not None and e.hand_id not in seated][:3]


def check_l3(report: Report, presets=L3_PRESETS) -> None:
    """Observation contains no foreign hole cards, deck order, seeds, or other tables' logs."""
    for preset in presets:
        cfg = load_preset(preset)
        agents = _pipeline_game(cfg, 3, f"gate-l-L3-{preset}")
        bad, decisions, cards = [], 0, 0
        for a in agents:
            for ho, obs, public, n_events in a.built:
                decisions += 1
                allowed = set(obs.hole_cards) | set(obs.board) | public
                bad += scan_leaks(ho, allowed)
                cards += sum(1 for _, v in _leaves(ho) if isinstance(v, str) and CARD.match(v))
                if tuple(ho.hole_cards) != tuple(obs.hole_cards):
                    bad.append("hole_cards differ from the player's own")
            bad += foreign_table_events(a.events, a.decisions[0][0].player_id if a.decisions else -1)
        report.check("L3", not bad and decisions > 0 and cards > 0,
                     f"{preset}: {bad[:3] or 'scan saw no decisions/cards'}. Build observations only through ObservationBuilder "
                     "and keep private objects out of Observation/Event.")


def check_l4(report: Report, preset: str = "6max_sng_wta") -> None:
    """Survivor count and prize structure show up in the very next observation."""
    cfg = load_preset(preset)
    agents = _pipeline_game(cfg, 5, "gate-l-L4")
    obs_list = [(ho, obs) for a in agents for ho, obs, *_ in a.built]
    wrong = [obs.hand_no for ho, obs in obs_list if ho.tournament["players_remaining"] != len(obs.seat_players)]
    report.check("L4", not wrong and len(obs_list) > 0,
                 f"{preset}: players_remaining disagrees with the seated survivors at rounds {sorted(set(wrong))[:5]}. "
                 "Take the count from the current round, not a cached value.")
    first = agents[0].built[0][1]
    builder = ObservationBuilder(cfg)
    fewer = dataclasses.replace(first, players_remaining=first.players_remaining - 1, all_stacks=first.all_stacks[:-1],
                                paid_places=first.paid_places - 1)
    ho = builder.build(fewer)
    report.check("L4", ho.tournament["players_remaining"] == first.players_remaining - 1
                 and ho.tournament["paid_places"] == first.paid_places - 1
                 and len(ho.tournament["stack_quantiles"]) == 9
                 and ho.tournament["avg_stack"] == float(np.mean(fewer.all_stacks)),
                 "changing survivors/paid places in the Observation did not change HeroObservation.tournament.")
    other = dataclasses.replace(cfg, payouts=(1.0,))
    report.check("L4", tuple(ObservationBuilder(other).build(first).tournament["prizes"]) == tuple(other.payout_amounts())
                 and tuple(ho.tournament["prizes"]) == tuple(cfg.payout_amounts()),
                 "changing the payout structure did not change tournament['prizes']; derive it from the config each call.")


def check_l5(make_agent: Callable[[], Agent], report: Report, preset: str = "6max_sng_wta") -> None:
    """A late joiner remembers only what happened after joining (memory store, builder and agent state)."""
    cfg = load_preset(preset)
    tap = record_game(cfg, 5, "gate-l-L5")
    table = tap.decisions[0][0].table_id
    mine = [e for e in tap.events if e.table_id == table]
    cut = next(i for i, e in enumerate(mine) if e.type == "NEW_HAND" and e.hand_id >= 4)
    join_hand = mine[cut].hand_id
    joined, full = GameMemoryStore(), GameMemoryStore()
    joined.start_game("gate-l-L5")
    full.start_game("gate-l-L5")
    for e in mine[cut:]:
        joined.observe(e)
    for e in mine:
        full.observe(e)
    j, f = joined.get("gate-l-L5"), full.get("gate-l-L5")
    ok = (0 < j.hands_seen < f.hands_seen
          and all(a.hand_id >= join_hand for a in j.recent_actions)
          and all(s.hand_id >= join_hand for s in j.showdowns)
          and all(j.opponents[p].hands <= f.opponents[p].hands for p in j.opponents))
    report.check("L5", ok, "late-join memory holds events from before the join. "
                 "Create memory in start_game at join time and never backfill earlier hands.")
    # agent level: whatever happened before the join must not matter to the joiner.
    obs, n = next((o, k) for o, k in tap.decisions if o.hand_id > join_hand)
    post = [e for e in tap.events[:n] if e.hand_id is not None and e.hand_id >= join_hand and e.table_id == obs.table_id]
    ps = []
    for seed in (21, 22):
        agent = make_agent()
        _feed(agent, "gate-l-other", record_game(cfg, seed, "gate-l-other").events)  # unrelated earlier life
        agent.on_game_end("gate-l-other")
        _feed(agent, obs.game_id, post)
        ps.append(policy_of(agent, obs))
    report.check("L5", ps[0] == ps[1], "late joiner's policy depends on events it never saw. Reset all state in on_game_start.")


def _l7_teacher() -> TeacherContext:
    # A fixed, assumption-only opponent model: raises pairs and broadways more, folds weak hands.
    def policy(cls: str, act: str) -> float:
        strong = cls[0] == cls[1] or (cls[0] in "AKQJT" and cls[1] in "AKQJT")
        return {"cbr": 0.8 if strong else 0.2, "cc": 0.5, "f": 0.05 if strong else 0.5}.get(act, 0.5)
    return TeacherContext("l7_fixture", "1", policy)


def contract_pipeline(obs: Observation, private: PrivateWorldState, teacher: TeacherContext,
                      builder: ObservationBuilder) -> tuple:
    """The production path: engine observation -> PublicObservation -> DecisionContext and teacher labels.

    `private` is handed in only because an engine has it; a correct pipeline never reads it.
    """
    po = builder.build(obs)
    dc = decision_context(po)
    opps = [k for k, s in enumerate(po.seats) if s.used and k != 0 and s.in_hand]
    labels = tuple(opp_range_label(po, teacher, k).tobytes() for k in opps)
    return repr(dc), labels


class _DeckRng:
    """Director rng whose n-th 52-card permutation (one per hand) can be replaced by a chosen deck."""

    def __init__(self, seed: int, decks: dict[int, list[int]] | None = None) -> None:
        self._g = np.random.default_rng(seed)
        self._decks = decks or {}
        self.dealt: list[list[int]] = []

    def permutation(self, n):
        p = self._g.permutation(n)
        if n == N_CARDS:
            i = len(self.dealt)
            p = np.array(self._decks.get(i, p))
            self.dealt.append([int(c) for c in p])
        return p

    def __getattr__(self, name):
        return getattr(self._g, name)


class _Stop(Exception):
    pass


class _Caller(Agent):
    """Always checks or calls, so the public action sequence does not depend on anyone's cards."""

    def act(self, observation: Observation):
        return Action("call")


class _HeroTap(_Caller):
    def __init__(self, rng: _DeckRng, hands: list, stop_at: int | None = None) -> None:
        self.rng, self.hands, self.stop_at = rng, hands, stop_at
        # (observation, index of its hand's deck, engine truth: hero hole cards + dealt board,
        #  every seat's hole cards)
        self.decisions: list[tuple[Observation, int, tuple[str, ...], dict[int, tuple[str, ...]]]] = []

    def act(self, observation: Observation):
        hand = self.hands[-1]
        st = hand.state
        holes = {seat: tuple(repr(c) for c in st.hole_cards[i]) for i, seat in enumerate(hand.seats)}
        truth = holes[observation.seat] + tuple(repr(c) for c in st.get_board_cards(0))
        self.decisions.append((observation, len(self.rng.dealt) - 1, truth, holes))
        if self.stop_at is not None and len(self.decisions) > self.stop_at:
            raise _Stop
        return super().act(observation)


def _play_until(cfg: TournamentConfig, seed: int, decks: dict, stop_at: int | None):
    # The truth about dealt cards is read from PokerKit state, not from Hand.board(), so the fixed
    # positions do not depend on the observation path under test.
    import stalker.tournament.director as director

    hands: list = []

    class _RecordingHand(director.Hand):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            hands.append(self)

    rng = _DeckRng(seed, decks)
    hero = _HeroTap(rng, hands, stop_at)
    agents = [hero] + [_Caller() for _ in range(cfg.players - 1)]
    real, director.Hand = director.Hand, _RecordingHand
    try:
        run_game(cfg, agents, rng, game_id="l7")
    except _Stop:
        pass
    finally:
        director.Hand = real
    return hero, rng


def hidden_worlds(cfg: TournamentConfig, seed: int, decision: int, n: int,
                  rng: np.random.Generator) -> list[tuple[Observation, PrivateWorldState]]:
    """Replay the engine n times up to the hero's `decision`-th decision, each time with a deck that keeps
    the hero's hole cards and the dealt board in place and shuffles every other card. Every world's
    observation is built by the director itself, so a leak anywhere on the engine -> observation path shows."""
    hero, base_rng = _play_until(cfg, seed, {}, decision)
    _, hand_idx, truth, _ = hero.decisions[decision]
    deck = base_rng.dealt[hand_idx]
    fixed = {CARD_INDEX[c] for c in truth}
    free_pos = [i for i, c in enumerate(deck) if c not in fixed]
    worlds = []
    for _ in range(n):
        d = list(deck)
        moved = [deck[i] for i in free_pos]
        for i, c in zip(free_pos, rng.permutation(moved)):
            d[i] = int(c)
        h, _ = _play_until(cfg, seed, {hand_idx: d}, decision)
        w_obs, _, _, holes = h.decisions[decision]
        worlds.append((w_obs, PrivateWorldState(holes, tuple(card_str(c) for c in d))))
    return worlds


def l7_decisions(cfg: TournamentConfig, seed: int, k: int) -> list[int]:
    """Hero decision indices: k//2 preflop ones facing an action, then postflop ones."""
    hero, _ = _play_until(cfg, seed, {}, None)
    pre = [i for i, (o, *_) in enumerate(hero.decisions) if not o.board and o.action_history]
    post = [i for i, (o, *_) in enumerate(hero.decisions) if o.board]
    return pre[: k // 2] + post[: k - k // 2]


def check_l7(report: Report, pipelines: dict[str, Callable] | None = None,
             agents: dict[str, Callable[[], Agent]] | None = None, preset: str = "6max_sng_wta") -> None:
    """L7: same public observation + same assumed opponent policy, only hidden cards and deck differ ->
    identical DecisionContext and teacher labels (each pipeline) and identical policy output (each agent)."""
    cfg = load_preset(preset)
    builder = ObservationBuilder(cfg)
    teacher = _l7_teacher()
    pipelines = pipelines if pipelines is not None else {"contract_v0": contract_pipeline}
    agents = agents if agents is not None else dict(REGISTRY)
    rng = np.random.default_rng(7)
    for d in l7_decisions(cfg, L7_SEED, L7_DECISIONS):
        worlds = hidden_worlds(cfg, L7_SEED, d, L7_WORLDS, rng)
        for name, pipe in pipelines.items():
            outs = {pipe(o, w, teacher, builder) for o, w in worlds}
            report.check("L7", len(outs) == 1,
                         f"[{name}] decision {d}: {len(outs)} different outputs across {L7_WORLDS} worlds that "
                         "differ only in hidden cards. Labels and policy inputs must be built from "
                         "PublicObservation + TeacherContext only (stalker/env/contract.py).")
        for name, make in agents.items():
            outs = {policy_of(make(), o) for o, _ in worlds}
            report.check("L7", len(outs) == 1,
                         f"[{name}] decision {d}: policy output differs across {L7_WORLDS} worlds that differ "
                         "only in hidden cards; the engine->observation path or the policy reads hidden state.")


def _l6_config() -> TournamentConfig:
    """Small hyper-turbo 6-max SNG: games end in seconds, so a training batch is cheap to build."""
    from stalker.tournament.config import BlindLevel

    return TournamentConfig(
        name="gate-l L6 hyper SNG", players=6, table_size=6, starting_stack=500,
        levels=(BlindLevel(10, 20, 0, 3), BlindLevel(25, 50, 0, 3), BlindLevel(50, 100, 0, 3),
                BlindLevel(100, 200, 0, 3), BlindLevel(200, 400, 0, 3), BlindLevel(500, 1000, 0, 3)),
        payouts=(0.5, 0.3, 0.2), buy_in=100)


def check_l6(report: Report, segments=None, trainer=None) -> None:
    """A training batch is cut at game_id, starts from zero state, and a segment replays alone as in the batch.

    `segments`/`trainer` let tests inject a corrupted batch; by default a fresh seeded trainer plays `L6_GAMES` games.
    """
    import torch
    from stalker.rl.train import TrainConfig, Trainer, check_segments

    if trainer is None:
        trainer = Trainer(_l6_config(), TrainConfig(seed=6, games_per_iter=1, epochs=1, minibatch_segments=6))
    if segments is None:
        segments = [s for g in range(L6_GAMES) for s in trainer.play_game(f"gate-l-L6-{g}")]
    try:
        check_segments(segments)
    except ValueError as e:
        report.check("L6", False, f"{e}")
        return
    games = {s.game_id for s in segments}
    report.check("L6", len(games) >= 2, f"batch has {len(games)} game(s); L6 needs at least 2 to show games stay apart.")
    ok = True
    mixed = trainer._replay(segments)
    for i, seg in enumerate(segments):
        alone = trainer._replay([seg])
        n = len(seg.actions)
        ok &= bool(torch.allclose(alone[0][0, :n], mixed[0][i, :n], atol=1e-6)
                   and torch.allclose(alone[1][0, :n], mixed[1][i, :n], atol=1e-6))
    report.check("L6", ok, "a segment's replayed logp/value changed with the other segments in its batch. "
                 "Replay each segment from a zero state and share nothing across the batch dimension.")


def _rl_policy_agent() -> Agent:
    from stalker.rl.env import TournamentEnv
    from stalker.rl.policy import Policy, PolicyConfig
    from stalker.rl.train import PolicyAgent

    cfg = load_preset("9max_sng_flat")  # table_size 9: the agent is probed on 6- and 9-max games (L1 uses both)
    n_actions = TournamentEnv(cfg).n_actions
    return PolicyAgent(Policy(PolicyConfig(variant="ai2", n_actions=n_actions), seed=0), cfg, np.random.default_rng(0))


def torch_available() -> bool:
    return importlib.util.find_spec("torch") is not None


def run_gate_l(agents: dict[str, Callable[[], Agent]] | None = None) -> Report:
    report = Report()
    if agents is None:
        agents = dict(REGISTRY)
        if torch_available():
            agents[RL_AGENT] = _rl_policy_agent
    for name, make in agents.items():
        sub = Report()
        check_l1(make, sub)
        check_l2(make, sub)
        check_l5(make, sub)
        for item, c in sub.counts.items():
            report.counts.setdefault(item, [0, 0])
            report.counts[item][0] += c[0]
            report.counts[item][1] += c[1]
        report.failures += [f"[{name}] {m}" for m in sub.failures]
        report.skipped += sub.skipped
    check_l3(report)
    check_l4(report)
    check_l7(report)
    if torch_available():
        check_l6(report)
    else:
        report.skipped.append(SKIP_TORCH)
    report.skipped = sorted(set(report.skipped))
    return report


def _random_agent() -> Agent:
    return RandomLegalAgent(np.random.default_rng(0))


def _reference_bot() -> Agent:
    return ReferenceBot(np.random.default_rng(0))


# Agents under test. Register a new policy here (referee-change) so every CI run checks its isolation.
# The RL PolicyAgent (RL_AGENT) is added by run_gate_l when torch is installed.
REGISTRY: dict[str, Callable[[], Agent]] = {"random_legal": _random_agent, "reference_bot_v1": _reference_bot}


def main() -> int:
    report = run_gate_l()
    for item, (p, t) in sorted(report.counts.items()):
        print(f"{item:4s} {p}/{t}")
    for s in report.skipped:
        print(f"skip {s}")
    if not report.ok:
        print("failures:")
        print("\n".join("  " + m for m in report.failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
