"""persona_fit (#569): the lever search is reproducible from its seed and never makes the loss worse."""
import numpy as np

from stalker.agents.persona_fit import LEVERS, current_levers, fit, loss, measure


def test_same_seed_same_levers_and_loss_not_worse():
    start = current_levers()
    kw = dict(hands=100, step=0.2, max_passes=1, types=("nit",))
    a = fit(start, rng=np.random.default_rng(3), **kw)
    b = fit(start, rng=np.random.default_rng(3), **kw)
    assert a == b
    lev, val = a
    assert set(lev) == set(start) and all(len(v) == len(LEVERS) and all(0 <= x <= 1 for x in v) for v in lev.values())
    assert {n: lev[n] for n in lev if n != "nit"} == {n: start[n] for n in lev if n != "nit"}
    assert val <= loss(measure(start, 100)) and val == loss(measure(lev, 100))
