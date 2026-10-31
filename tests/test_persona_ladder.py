import numpy as np
import pytest

from stalker.agents.persona import PRESETS, PersonaAgent, persona_params
from stalker.agents.persona_stats import measure_session
from stalker.cash.presets import preset
from stalker.cash.session import run_cash_session
from stalker.personas import MAX_LEVEL, MIN_LEVEL, ladder, level


def _agents(names_or_params, seed):
    ss = np.random.SeedSequence(seed).spawn(len(names_or_params))
    return [PersonaAgent(p, np.random.default_rng(s)) for p, s in zip(names_or_params, ss)]


def test_ladder_shape_and_determinism():
    lad = ladder()
    assert sorted(lad) == list(range(1, 20)) and lad == ladder()
    assert lad[1] == persona_params("calling_station") and lad[19] == persona_params("high_stakes_pro")
    vp = [lad[n].vpip for n in lad]
    assert vp == sorted(vp, reverse=True)  # tightens with level


@pytest.mark.parametrize("bad", [0, 20, -1, 1.5, "3", None, True])
def test_level_out_of_range(bad):
    with pytest.raises(ValueError, match="1..19"):
        level(bad)


def test_presets_unchanged():
    assert len(PRESETS) == 9 and persona_params("tag").vpip == 0.22


def test_fidelity_levels_1_7_13_19():
    lv = (1, 7, 13, 19)
    params = [level(n) for n in lv] + [persona_params("tag")] * 2
    stats = measure_session(_agents(params, 5), 20_000, seed=31)
    bad = [f"L{n} {k}: target {getattr(level(n), k):.3f} measured {getattr(st, k):.3f}"
           for n, st in zip(lv, stats) for k in ("vpip", "pfr") if abs(getattr(st, k) - getattr(level(n), k)) > 0.05]
    assert not bad, bad


def test_level_19_beats_level_1_headsup():
    cfg = preset("cash_6max_100bb", hands=6000)
    total = 0.0
    for seed in range(2):  # seat swap: both orders
        for order in ((19, 1), (1, 19)):
            agents = _agents([level(n) for n in order] + [persona_params("tag")] * 4, seed)
            res = run_cash_session(cfg, agents, np.random.default_rng(100 + seed))
            total += res.net[order.index(19)] - res.net[order.index(1)]
    assert total > 0
