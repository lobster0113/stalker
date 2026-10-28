import numpy as np
import pytest

from referee.e2.exploiter import head_to_head
from stalker.agents.persona import PRESETS, PersonaParams
from stalker.e2 import game as G
from stalker.e2.abstraction import BASELINE
from stalker.e2.personas import Persona, field


def _walk(policy, hands, seed):
    rng = np.random.default_rng(seed)
    for _ in range(hands):
        s = G.deal(rng)
        while not s.done:
            p = policy(s)
            yield s, p
            s = G.apply(s, G.legal(s)[int(rng.choice(len(p), p=p))])


def test_every_preset_is_a_deterministic_distribution_over_legal_actions():
    assert [p.name for p in field()] == list(PRESETS)
    for persona in field():
        for s, p in _walk(persona, 15, seed=226):
            assert p.shape == (len(G.legal(s)),) and np.isclose(p.sum(), 1) and (p >= 0).all()
            assert np.array_equal(p, persona(s))


def _sb_open_rates(params, n=3000):
    rng = np.random.default_rng(7)
    pol = Persona("x", params)
    vpip = pfr = 0
    for _ in range(n):
        s = G.deal(rng)
        acts = G.legal(s)
        a = acts[int(np.argmax(pol(s)))]   # preflop decisions are pure
        vpip += a != "f"
        pfr += a in ("r", "a")
    return vpip / n, pfr / n


def test_preflop_frequencies_follow_the_parameters():
    lo = _sb_open_rates(PersonaParams(0.15, 0.05, 0.5, 0.5))
    hi = _sb_open_rates(PersonaParams(0.45, 0.30, 0.5, 0.5))
    assert lo[0] < hi[0] and lo[1] < hi[1]
    assert lo[0] == pytest.approx(0.15, abs=0.04) and hi[1] == pytest.approx(0.30, abs=0.04)


def test_uniform_random_loses_to_tag():
    m, se = head_to_head({}, BASELINE, Persona("tag"), BASELINE, 1500, seed=3)
    assert m + 2 * se < 0
