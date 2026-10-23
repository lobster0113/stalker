import dataclasses
import re

import numpy as np
import pytest

from stalker.agents.base import Action, Agent, Event, Observation
from stalker.agents.random_agent import RandomLegalAgent
from stalker.observe.builder import MAX_SEATS, STACK_QUANTILES, HeroObservation, ObservationBuilder
from stalker.observe.memory import GameMemoryStore, MemoryBoundaryError
from stalker.tournament.config import load_preset, preset_names
from stalker.tournament.director import run_game

CARD = re.compile(r"^[2-9TJQKA][cdhs]$")
FORBIDDEN_KEYS = ("seed", "deck", "rng", "generator")


def _leaves(x, path=""):
    """Yield (path, leaf) over dataclasses, dicts and sequences."""
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


class Recorder(RandomLegalAgent):
    """Random bot that builds a HeroObservation per decision and keeps its own game memory."""

    def __init__(self, rng, cfg):
        super().__init__(rng)
        self.builder, self.store, self.built = ObservationBuilder(cfg), GameMemoryStore(), []
        self.public_cards: set[str] = set()
        self.game_id = None

    def on_game_start(self, game_id):
        self.game_id = game_id
        self.store.start_game(game_id)

    def observe(self, event):
        self.store.observe(event)
        if event.type == "SHOWDOWN":
            self.public_cards |= {c for cards in event.data["hands"].values() for c in cards}
            self.public_cards |= set(event.data["board"])

    def act(self, obs):
        ho = self.builder.build(obs, self.store.get(self.game_id))
        self.built.append((ho, set(obs.hole_cards), set(obs.board), set(self.public_cards)))
        return super().act(obs)

    def on_game_end(self, game_id):
        self.store.end_game(game_id)


def _run(preset="6max_sng_wta", seed=1):
    cfg = load_preset(preset)
    agents = [Recorder(np.random.default_rng([seed, i]), cfg) for i in range(cfg.players)]
    res = run_game(cfg, agents, np.random.default_rng(seed), game_id=f"g{seed}")
    return cfg, agents, res


def test_no_private_information_in_observation():
    _, agents, _ = _run()
    seen = 0
    for a in agents:
        for ho, hole, board, public in a.built:
            allowed = hole | board | public
            for path, leaf in _leaves(ho):
                if isinstance(leaf, str) and CARD.match(leaf):
                    seen += 1
                    assert leaf in allowed, f"unexpected card {leaf} at {path}: only own hole, board and showdowns are allowed."
                for bad in FORBIDDEN_KEYS:
                    assert bad not in path.lower(), f"forbidden field {path}."
    assert seen > 0


def test_observation_shape_is_fixed_and_masked():
    cfg, agents, _ = _run("9max_sng_flat")
    for ho, *_ in agents[0].built:
        assert len(ho.seats) == MAX_SEATS
        assert ho.seats[0].is_hero and ho.seats[0].used
        assert len(ho.tournament["stack_quantiles_bb"]) == len(STACK_QUANTILES)
        assert all(not s.used and s.stack == 0 for s in ho.seats[cfg.table_size:])
        assert ho.legal["call"]
        assert ho.pot_bb == pytest.approx(ho.pot / ho.tournament["blinds"]["bb"])


def test_stack_distribution_is_tournament_wide():
    cfg, agents, _ = _run("6max_sng_wta")
    first = agents[0].built[0][0]
    assert first.tournament["players_remaining"] == cfg.players
    assert first.tournament["avg_stack"] == pytest.approx(cfg.starting_stack)
    assert first.tournament["stack_quantiles"][0] == first.tournament["stack_quantiles"][-1] == cfg.starting_stack


def test_memory_is_empty_after_game_and_boundary_errors():
    _, agents, _ = _run()
    for a in agents:
        assert a.store.game_id is None
        with pytest.raises(MemoryBoundaryError):
            a.store.get("g1")


def test_game_id_mixing_raises():
    s = GameMemoryStore()
    with pytest.raises(MemoryBoundaryError):
        s.observe(Event("NEW_HAND", "a", 1, 0, {"seat_players": {}}))
    s.start_game("a")
    with pytest.raises(MemoryBoundaryError):
        s.observe(Event("NEW_HAND", "b", 1, 0, {"seat_players": {}}))
    with pytest.raises(MemoryBoundaryError):
        s.start_game("b")
    with pytest.raises(MemoryBoundaryError):
        s.end_game("b")
    s.end_game("a")
    s.start_game("b")
    assert s.get("b").hands_seen == 0  # nothing carried over from game a


def test_builder_rejects_memory_of_other_game():
    cfg, agents, _ = _run()
    store = GameMemoryStore()
    mem = store.start_game("other")
    a = agents[0]
    obs_holder = {}

    class Spy(RandomLegalAgent):
        def act(self, obs):
            obs_holder.setdefault("obs", obs)
            return super().act(obs)

    run_game(cfg, [Spy(np.random.default_rng(i)) for i in range(cfg.players)], np.random.default_rng(3), game_id="g3")
    with pytest.raises(MemoryBoundaryError):
        a.builder.build(obs_holder["obs"], mem)


def _ev(t, hand=1, **data):
    return Event(t, "g", hand, 0, data)


def test_statistics_and_late_join():
    s = GameMemoryStore(recent_k=2)
    s.start_game("g")
    s.observe(_ev("NEW_HAND", seat_players={0: 10, 1: 11}))
    act = lambda p, a, street, facing, amt=0: s.observe(
        _ev("ACTION", player_id=p, action={"f":"fold","c":"call","r":"raise"}[a], street=street, facing_bet=facing, amount=amt, seat=p - 10, pot=0))
    act(10, "c", 0, True, 5)   # SB completes: voluntary
    act(11, "c", 0, False)     # BB checks: not voluntary
    act(10, "r", 1, False, 20)
    act(11, "f", 1, True)
    s.observe(_ev("HAND_END"))
    m = s.get("g")
    a, b = m.opponents[10], m.opponents[11]
    assert (a.hands, a.vpip_hands, a.pfr_hands) == (1, 1, 0)
    assert (b.hands, b.vpip_hands) == (1, 0)
    assert a.actions["pre_facing"]["c"] == 1 and a.actions["post_open"]["r"] == 1
    assert b.opportunities["post_facing"] == 1 and b.actions["post_facing"]["f"] == 1
    assert [x.action for x in m.recent_actions] == ["r", "f"]  # last K=2 only
    s.observe(_ev("NEW_HAND", hand=2, seat_players={0: 10, 1: 11}))
    act(10, "r", 0, True, 30)
    s.observe(_ev("SHOWDOWN", hand=2, board=("2c", "3c", "4c", "5c", "6c"), hands={0: ("As", "Ad")}))
    s.observe(_ev("HAND_END", hand=2))
    assert (m.opponents[10].pfr_hands, m.opponents[10].vpip_hands, m.opponents[10].showdowns) == (1, 2, 1)
    assert m.showdowns[0].hole_cards == ("As", "Ad")


def test_mid_game_join_remembers_only_after_join():
    cfg = load_preset("6max_sng_wta")
    events: list[Event] = []
    agents = [RandomLegalAgent(np.random.default_rng(i)) for i in range(cfg.players)]
    run_game(cfg, agents, np.random.default_rng(5), observer=events.append, game_id="gj")
    table = next(e.table_id for e in events if e.type == "NEW_HAND")
    mine = [e for e in events if e.table_id == table]
    cut = next(i for i, e in enumerate(mine) if e.type == "NEW_HAND" and e.hand_id >= 4)
    s = GameMemoryStore()
    s.start_game("gj")
    for e in mine[cut:]:
        s.observe(e)
    full = GameMemoryStore()
    full.start_game("gj")
    for e in mine:
        full.observe(e)
    assert 0 < s.get("gj").hands_seen < full.get("gj").hands_seen
    assert all(s.get("gj").opponents[p].hands <= full.get("gj").opponents[p].hands for p in s.get("gj").opponents)
