import dataclasses
import math
from collections import defaultdict

import numpy as np
import pytest

from stalker.agents.base import Action, Agent, Observation
from stalker.agents.random_agent import RandomLegalAgent
from stalker.tournament.config import ConfigError, load_preset, preset_names
from stalker.tournament.director import rank_busts, run_game


class Passive(Agent):
    """Mostly calls, rarely folds or min-raises, so games last several rounds and thin out gradually."""

    def __init__(self, rng):
        self.rng = rng

    def act(self, obs: Observation) -> Action:
        r = self.rng.random()
        la = obs.legal
        if la.can_fold and la.call_amount > 0 and r < 0.15:
            return Action("fold")
        if la.min_raise_to is not None and r > 0.93:
            return Action("raise", la.min_raise_to)
        return Action("call")


def _agents(cls, n, seed=0):
    return [cls(np.random.default_rng([seed, i])) for i in range(n)]


def _play(preset, cls=Passive, seed=0, **kw):
    cfg = load_preset(preset)
    events = []
    res = run_game(cfg, _agents(cls, cfg.players, seed), np.random.default_rng(seed), observer=events.append, **kw)
    return cfg, res, events


def test_rank_busts_larger_start_stack_ranks_higher():
    rng = np.random.default_rng(0)
    assert rank_busts([(1, 50), (2, 300), (3, 120)], rng) == [2, 3, 1]


def test_rank_busts_tie_is_random_but_reproducible():
    orders = set()
    for seed in range(30):
        a = rank_busts([(1, 100), (2, 100), (3, 40)], np.random.default_rng(seed))
        assert a == rank_busts([(1, 100), (2, 100), (3, 40)], np.random.default_rng(seed))
        assert a[2] == 3
        orders.add(tuple(a))
    assert orders == {(1, 2, 3), (2, 1, 3)}


@pytest.mark.parametrize("preset", ["mtt54", "9max_sng_flat"])
def test_simultaneous_busts_rank_by_start_stack(preset):
    for seed in range(5):
        cfg, res, events = _play(preset, RandomLegalAgent, seed=seed)
        start, busted = {}, defaultdict(list)  # round -> [(player, start stack)]
        for e in events:
            if e.type == "NEW_HAND":
                start[e.hand_id] = e.data
            elif e.type == "HAND_END":
                d = start[e.hand_id]
                for seat, fs in e.data["final_stacks"].items():
                    if fs == 0:
                        busted[d["hand_no"]].append((d["seat_players"][seat], d["stacks"][seat]))
        for group in busted.values():
            by_rank = sorted(group, key=lambda b: res.ranks[b[0]])
            stacks = [s for _, s in by_rank]
            assert stacks == sorted(stacks, reverse=True), "better rank must have started the hand with >= chips"
            ranks = [res.ranks[p] for p, _ in group]
            assert len(set(ranks)) == len(ranks)


def test_attrition_through_small_fields_and_final_table():
    sizes_seen = set()
    for seed in range(8):
        _, _, events = _play("9max_sng_flat", seed=seed)
        per_round = defaultdict(list)
        for e in events:
            if e.type == "NEW_HAND":
                per_round[e.data["hand_no"]].append(len(e.data["seat_players"]))
        sizes_seen |= {sum(v) for v in per_round.values()}
    assert {5, 4, 3, 2} <= sizes_seen


@pytest.mark.parametrize("preset", ["mtt54", "mtt180_bbante", "6max_sng_wta"])
def test_balancing_and_table_breaking(preset):
    for seed in range(3):
        cfg, res, events = _play(preset, RandomLegalAgent, seed=seed)
        per_round = defaultdict(list)
        for e in events:
            if e.type == "NEW_HAND":
                per_round[e.data["hand_no"]].append(len(e.data["seat_players"]))
        n_tables = []
        for r, sizes in per_round.items():
            alive = sum(sizes)
            assert max(sizes) - min(sizes) <= 1, f"round {r}: tables {sizes} differ by more than 1"
            assert len(sizes) == math.ceil(alive / cfg.table_size), f"round {r}: {len(sizes)} tables for {alive}"
            n_tables.append(len(sizes))
        assert n_tables[0] == math.ceil(cfg.players / cfg.table_size)
        assert n_tables[-1] == 1
        assert n_tables == sorted(n_tables, reverse=True)


_GATE_R_PRESETS = [pytest.param(p, marks=pytest.mark.slow) if p == "mtt180_bbante" else p for p in preset_names()]


@pytest.mark.parametrize("preset", _GATE_R_PRESETS)
def test_gate_r_invariants_random_legal_bots(preset):
    cfg = load_preset(preset)
    for seed in range(20):
        events = []
        res = run_game(cfg, _agents(RandomLegalAgent, cfg.players, seed), np.random.default_rng(seed),
                       observer=events.append)
        assert res.illegal_actions == 0
        assert sorted(res.ranks) == list(range(1, cfg.players + 1))
        assert res.ranks.count(1) == 1
        assert sum(res.prizes) == pytest.approx(cfg.prize_pool)
        paid = len(cfg.payouts)
        for p, rank in enumerate(res.ranks):
            assert (res.prizes[p] > 0) == (rank <= paid and cfg.payout_amounts()[rank - 1] > 0)
        for e in events:
            if e.type == "HAND_END":  # chips are conserved within every hand
                assert sum(e.data["deltas"].values()) == 0


def test_reproducible_and_seed_sensitive():
    _, a, ev_a = _play("6max_sng_topheavy", seed=3)
    _, b, ev_b = _play("6max_sng_topheavy", seed=3)
    _, c, _ = _play("6max_sng_topheavy", seed=4)
    assert a == b
    assert [dataclasses.astuple(e) for e in ev_a] == [dataclasses.astuple(e) for e in ev_b]
    assert a.ranks != c.ranks


def test_ids_and_event_stream_shape():
    cfg, res, events = _play("6max_sng_topheavy", game_id="g7", tournament_id="t9")
    assert (res.game_id, res.tournament_id) == ("g7", "t9")
    assert events[0].type == "START_GAME" and events[-1].type == "END_GAME"
    assert {e.game_id for e in events} == {"g7"}
    hand_ids = [e.hand_id for e in events if e.type == "NEW_HAND"]
    assert hand_ids == sorted(set(hand_ids)) and len(hand_ids) == res.hands
    open_hand = None
    for e in events[1:-1]:
        if e.type == "NEW_HAND":
            assert open_hand is None
            open_hand = e.hand_id
        elif e.type == "HAND_END":
            assert open_hand == e.hand_id
            open_hand = None
        else:
            assert e.type in ("ACTION", "SHOWDOWN") and e.hand_id == open_hand
    assert open_hand is None


def test_only_showdown_reveals_hole_cards_and_agents_see_own_cards_only():
    class Spy(Passive):
        def __init__(self, rng):
            super().__init__(rng)
            self.obs, self.events, self.log = [], [], []

        def on_game_start(self, game_id):
            self.log.append("start")

        def on_game_end(self, game_id):
            self.log.append("end")

        def observe(self, event):
            self.events.append(event)

        def act(self, obs):
            self.obs.append(obs)
            return super().act(obs)

    cfg = load_preset("6max_sng_wta")
    agents = _agents(Spy, cfg.players)
    events = []
    run_game(cfg, agents, np.random.default_rng(0), observer=events.append)
    for e in events:
        if e.type != "SHOWDOWN":
            assert "hands" not in e.data and "hole_cards" not in e.data
    shows = [e for e in events if e.type == "SHOWDOWN"]
    assert shows, "random-ish play should reach at least one showdown"
    for e in shows:
        assert len(e.data["hands"]) >= 2
    for a in agents:
        assert a.log == ["start", "end"]
        for o in a.obs:
            assert len(o.hole_cards) == 2 and not set(o.hole_cards) & set(o.board)
            assert o.legal.seat == o.seat and o.seat_players[o.seat] == o.player_id
        # agents only receive events from their own table
        assert all(e.table_id is not None for e in a.events)


def test_illegal_action_falls_back_and_is_counted():
    class Sometimes(RandomLegalAgent):
        def __init__(self, rng):
            super().__init__(rng)
            self.n = 0

        def act(self, obs):
            self.n += 1
            if self.n % 2 == 0:  # raise above the stack: illegal
                return Action("raise", (obs.legal.max_raise_to or 0) + 1_000_000)
            return super().act(obs)

    cfg = load_preset("6max_sng_wta")
    res = run_game(cfg, _agents(Sometimes, cfg.players), np.random.default_rng(0))
    assert res.illegal_actions > 0
    assert sorted(res.ranks) == list(range(1, cfg.players + 1))


def test_input_validation():
    cfg = load_preset("6max_sng_wta")
    with pytest.raises(ValueError, match="need 6 agents"):
        run_game(cfg, _agents(Passive, 5), np.random.default_rng(0))
    for field, value in (("length_unit", "minutes"), ("short_stack_rule", "skip")):
        bad = dataclasses.replace(cfg, **{field: value})
        with pytest.raises(ConfigError, match="not implemented"):
            run_game(bad, _agents(Passive, 6), np.random.default_rng(0))


def test_folded_seats_leave_the_hand_and_are_never_shown():
    log = []  # events and observations in the order the director produced them

    class Spy(Passive):
        def act(self, obs):
            log.append(obs)
            return super().act(obs)

    cfg = load_preset("6max_sng_wta")
    run_game(cfg, _agents(Spy, cfg.players), np.random.default_rng(0), observer=log.append)
    folded = defaultdict(set)  # hand_id -> seats that have folded so far
    shows = folds = 0
    for item in log:
        if isinstance(item, Observation):
            assert not set(item.in_hand) & folded[item.hand_id]
        elif item.type == "ACTION" and item.data["action"] == "fold":
            folded[item.hand_id].add(item.data["seat"])
            folds += 1
        elif item.type == "SHOWDOWN":
            assert not set(item.data["hands"]) & folded[item.hand_id]
            shows += 1
    assert folds and shows


class _OrderProbe(Passive):
    seen: list = []

    def act(self, obs: Observation) -> Action:
        _OrderProbe.seen.append(obs)
        return super().act(obs)


def _expected_first(obs: Observation) -> int:
    """Preflop opener when nobody has acted yet: UTG (the button heads-up), skipping blind posters who are all-in."""
    seats = sorted(obs.stacks)
    after = [s for s in seats if s > obs.button] + [s for s in seats if s <= obs.button]
    order = [obs.button, after[0]] if len(after) == 2 else after[2:] + after[:2]
    return next(s for s in order if obs.stacks[s] > 0)


@pytest.mark.parametrize("preset,mode", [("mtt54", "classic"), ("mtt180_bbante", "bb_ante"),
                                         ("6max_sng_wta", "none"), ("9max_sng_flat", "none")])
def test_observation_ante_mode_and_action_order(preset, mode):
    _OrderProbe.seen = []
    cfg, _, _ = _play(preset, _OrderProbe)
    seen = _OrderProbe.seen
    assert seen
    flop = 0
    for obs in seen:
        assert obs.ante_mode == (mode if obs.ante else "none")
        order = obs.action_order
        assert order[0] == obs.seat and len(set(order)) == len(order)
        assert set(order) <= set(obs.in_hand)
        assert all(obs.stacks[s] > 0 for s in order)
        # seats act in clockwise order starting from the actor
        clockwise = sorted(order, key=lambda s: (s - obs.seat) % cfg.table_size)
        assert list(order) == clockwise
        if not obs.action_history:
            assert obs.seat == _expected_first(obs)
        flop += bool(obs.board)
    assert flop
