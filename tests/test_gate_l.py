import dataclasses

import numpy as np

from referee import gate_l
from referee.gate_l import Report, check_l1, check_l2, check_l5, foreign_table_events, scan_leaks
from stalker.agents.base import Action, Agent, Event
from stalker.agents.random_agent import RandomLegalAgent
from stalker.observe.memory import GameMemoryStore

_LEAKY: dict[int, int] = {}  # the violation: opponent stats kept outside the game


def _raise_share(raises: int, actions: int) -> dict:
    p = 0.1 + 0.8 * raises / max(actions, 1)
    return {"raise": p, "call": 1 - p}


class GlobalDictAgent(Agent):
    """Violates L1: opponent raise counts live in a module-level dict that survives game boundaries."""

    def observe(self, event):
        if event.type == "ACTION":
            _LEAKY[-1] = _LEAKY.get(-1, 0) + 1
            if event.data["action"] == "raise":
                _LEAKY[0] = _LEAKY.get(0, 0) + 1

    def action_probs(self, obs):
        return _raise_share(_LEAKY.get(0, 0), _LEAKY.get(-1, 0))

    def act(self, obs):
        return Action("call")


class MemoryAgent(Agent):
    """Honest memory user: stats live in a GameMemoryStore that is created and dropped with the game."""

    uses_memory = True

    def __init__(self):
        self.store, self.gid = GameMemoryStore(), None

    def on_game_start(self, game_id):
        self.gid = game_id
        self.store.start_game(game_id)

    def observe(self, event):
        self.store.observe(event)

    def on_game_end(self, game_id):
        self.store.end_game(game_id)

    def action_probs(self, obs):
        mem = self.store.get(obs.game_id)
        raises = sum(s.actions[c]["r"] for s in mem.opponents.values() for c in s.actions)
        total = sum(s.opportunities[c] for s in mem.opponents.values() for c in s.opportunities)
        return _raise_share(raises, total)

    def act(self, obs):
        return Action("call")


class DeclaresButIgnores(RandomLegalAgent):
    uses_memory = True


class LateJoinLeaker(MemoryAgent):
    """Violates L5: remembers an unrelated earlier game by never resetting a counter."""

    seen = 0

    def observe(self, event):
        type(self).seen += 1
        super().observe(event)

    def action_probs(self, obs):
        return _raise_share(type(self).seen, 100000)


def _rep(fn, make, **kw):
    r = Report()
    fn(make, r, **kw)
    return r


def test_l1_passes_for_stateless_and_honest_memory_agents():
    for make in (lambda: RandomLegalAgent(np.random.default_rng(0)), MemoryAgent):
        r = _rep(check_l1, make)
        assert r.ok, r.failures
        assert r.counts["L1"] == [2, 2]


def test_l1_detects_global_dict_agent():
    _LEAKY.clear()
    r = _rep(check_l1, GlobalDictAgent)
    assert not r.ok
    assert "game_id" in r.failures[0]  # message says how to fix


def test_l2_skipped_without_uses_memory_and_passes_for_memory_agent():
    r = _rep(check_l2, lambda: RandomLegalAgent(np.random.default_rng(0)))
    assert r.ok and not r.counts and "uses_memory" in r.skipped[0]
    r = _rep(check_l2, MemoryAgent)
    assert r.ok and r.counts["L2"] == [1, 1]


def test_l2_fails_when_declared_memory_is_ignored():
    r = _rep(check_l2, lambda: DeclaresButIgnores(np.random.default_rng(0)))
    assert not r.ok and "ignored" in r.failures[0]


def test_l5_passes_and_detects_leftover_state():
    assert _rep(check_l5, MemoryAgent).ok
    LateJoinLeaker.seen = 0
    r = _rep(check_l5, LateJoinLeaker)
    assert not r.ok and "never saw" in r.failures[0]


def test_l3_scan_flags_foreign_card_and_forbidden_field():
    agents = gate_l._pipeline_game(gate_l.load_preset("6max_sng_wta"), 1, "t")
    ho, obs, public, _ = agents[0].built[0]
    allowed = set(obs.hole_cards) | set(obs.board) | public
    assert scan_leaks(ho, allowed) == []
    other = next(c for c in ("As", "Kd", "7h", "2c", "Qs", "9d") if c not in allowed)
    leaked = dataclasses.replace(ho, board=ho.board + (other,))
    assert any(other in m for m in scan_leaks(leaked, allowed))
    seeded = dataclasses.replace(ho, tournament={**ho.tournament, "rng_seed": 3})
    assert any("forbidden" in m for m in scan_leaks(seeded, allowed))


def test_l3_foreign_table_events_are_flagged():
    ev = [Event("NEW_HAND", "g", 1, 0, {"seat_players": {0: 5}}), Event("ACTION", "g", 1, 0, {}),
          Event("ACTION", "g", 2, 1, {})]
    assert foreign_table_events(ev, 5) and "hand 2" in foreign_table_events(ev, 5)[0]
    assert foreign_table_events(ev[:2], 5) == []


def test_pipeline_checks_pass_and_gate_runner_reports():
    r = Report()
    gate_l.check_l3(r)
    gate_l.check_l4(r)
    assert r.ok, r.failures
    full = gate_l.run_gate_l()
    assert full.ok, full.failures
    assert any("L6" in s for s in full.skipped) or full.counts["L6"][1] > 0
