import dataclasses

import numpy as np
import pytest

from referee.gate_l import _PipelineAgent, foreign_table_events, scan_leaks
from stalker.agents.base import Action
from stalker.agents.persona import PRESETS, PersonaAgent, PersonaParams, persona_params
from stalker.agents.persona_stats import measure_session
from stalker.tournament.config import load_preset
from stalker.tournament.director import run_game

NAMES = sorted(PRESETS)
GROUPS = [NAMES[i:i + 3] for i in range(0, 9, 3)]  # three personas under test + three tag fillers per 6-max table


def _agents(names, seed):
    ss = np.random.SeedSequence(seed).spawn(6)
    seats = [*names, "tag", "tag", "tag"]
    return [PersonaAgent(persona_params(n), np.random.default_rng(s)) for n, s in zip(seats, ss)]


def _fidelity(hands, tol):
    bad = []
    for gi, names in enumerate(GROUPS):
        stats = measure_session(_agents(names, gi), hands, seed=100 + gi)
        for n, st in zip(names, stats):
            p = PRESETS[n]
            for key in ("vpip", "pfr"):
                if abs(getattr(st, key) - getattr(p, key)) > tol:
                    bad.append(f"{n} {key}: target {getattr(p, key):.3f} measured {getattr(st, key):.3f}")
            # aggression is reported, with a loose bound: fold_to_bet filters weak hands, so tight types read high
            if st.aggression is None or abs(st.aggression - p.aggression) > 0.25:
                bad.append(f"{n} aggression: target {p.aggression:.2f} measured {st.aggression}")
    assert not bad, bad


def test_nine_presets_and_table_values():
    assert len(PRESETS) == 9
    assert dataclasses.astuple(persona_params("calling_station")) == (0.55, 0.05, 0.12, 0.12)
    assert dataclasses.astuple(persona_params("maniac")) == (0.62, 0.42, 0.85, 0.25)
    assert dataclasses.astuple(persona_params("weak_tight")) == (0.17, 0.08, 0.22, 0.78)
    assert dataclasses.astuple(persona_params("nit"))[:2] == (0.12, 0.10)
    with pytest.raises(KeyError):
        persona_params("nobody")
    with pytest.raises(ValueError):
        PersonaParams(0.1, 0.2, 0.5, 0.5)


def test_fidelity_20k_hands_within_5pp():
    _fidelity(20_000, 0.05)


@pytest.mark.slow
def test_fidelity_100k_hands_within_3pp():
    _fidelity(100_000, 0.03)


def test_same_seed_same_actions():
    def run(seed):
        log = []
        agents = _agents(NAMES[:3], seed)
        for a in agents:
            inner = a.act
            a.act = lambda o, inner=inner: log.append(r := inner(o)) or r
        stats = measure_session(agents, 300, seed=7)
        return log, stats

    (la, sa), (lb, sb) = run(1), run(1)
    assert la == lb and sa == sb and len(la) > 300
    assert all(isinstance(x, Action) for x in la)
    assert run(2)[0] != la


class _SeatedPersona(_PipelineAgent):
    """_PipelineAgent whose actions come from a PersonaAgent, so the L3 scan covers the persona's own games."""

    def __init__(self, persona, cfg):
        super().__init__(np.random.default_rng(0), cfg)
        self.persona, self.acted = persona, 0

    def act(self, observation):
        mem = self.store.get(observation.game_id)
        self.built.append((self.builder.build(observation, mem), observation, set(self.public), len(self.events)))
        self.decisions.append((observation, len(self.events)))
        self.acted += 1
        return self.persona.act(observation)


def test_persona_passes_gate_l_l3_scan():
    # Seat PersonaAgents in a real game; every observation they receive goes through ObservationBuilder + scan_leaks.
    cfg = load_preset("6max_sng_wta")
    ss = np.random.SeedSequence(3).spawn(cfg.players)
    agents = [_SeatedPersona(PersonaAgent(persona_params(NAMES[i % len(NAMES)]), np.random.default_rng(s)), cfg)
              for i, s in enumerate(ss)]
    run_game(cfg, agents, np.random.default_rng(3), game_id="persona-l3")
    bad, decisions = [], 0
    for a in agents:
        for ho, obs, public, _ in a.built:
            decisions += 1
            bad += scan_leaks(ho, set(obs.hole_cards) | set(obs.board) | public)
        bad += foreign_table_events(a.events, a.decisions[0][0].player_id if a.decisions else -1)
    assert decisions > 0 and sum(a.acted for a in agents) == decisions
    assert not bad, bad[:3]

