"""scripts/persona_cell_grid.py judges a point with the same guards and values as the mixed-field test (#730)."""
import importlib.util
import pathlib

import numpy as np
import pytest

from stalker.agents.persona import PRESETS_V2, PersonaAgent
from stalker.agents.persona_stats import measure_session

_spec = importlib.util.spec_from_file_location("persona_cell_grid", pathlib.Path(__file__).parents[1] / "scripts/persona_cell_grid.py")
grid = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(grid)


def test_guard_constants_match_the_mixed_field_test():
    src = (pathlib.Path(__file__).parent / "test_persona_v2.py").read_text(encoding="utf-8")
    for frag in ("> 0.06", "< (0.95, 0.80)[i]", "err <= 0.14", "river <= 0.22", "> 0.05"):
        assert frag in src, frag  # a changed guard in the test must be mirrored in the script
    assert (grid.TOL, grid.TURN_CAP, grid.RIVER_CAP, grid.TURN_ERR, grid.RIVER_ERR, grid.FIDELITY_TOL) == (0.06, 0.95, 0.80, 0.14, 0.22, 0.05)


def test_build_points_keeps_start_and_caps_count():
    g = {t: {k: tuple(v) for k, v in grid.DEFAULT_GRID.items()} for t in grid.CELLS}
    pts = grid.build_points(g, 10, 0)
    assert len(pts) == 10 and len({repr(p) for p in pts}) == 10
    assert pts[0] == {t: {k: getattr(PRESETS_V2[t], k) for k in grid.LEVERS} for t in grid.CELLS}
    assert grid.build_points(g, 10, 0) == pts


@pytest.mark.slow
def test_current_presets_pass_with_the_same_errors_as_the_test():
    res = grid.evaluate(PRESETS_V2)
    assert res["passed"], res["violations"]
    fold = {}
    for gi, grp in enumerate(grid.TABLES):
        ss = np.random.SeedSequence(gi).spawn(6)
        agents = [PersonaAgent(PRESETS_V2[n], np.random.default_rng(s)) for n, s in zip(grp, ss)]
        for n, st in zip(grp, measure_session(agents, 20000, seed=50 + gi)):
            fold.setdefault(n, []).append((st.fold_cbet_turn, st.fold_river))
    mean = {n: [np.mean([f[i] for f in v if f[i] is not None]) for i in (0, 1)] for n, v in fold.items()}
    for i, key in enumerate(("turn_err", "river_err")):
        want = np.mean([abs(mean[n][i] - getattr(PRESETS_V2[n], ("fold_cbet_turn", "fold_river")[i])) for n in grid.TYPES])
        assert res[key] == pytest.approx(want, abs=5e-5)


def _test_seeds_replay(hands):
    # the mixed-field test's own loop (tests/test_persona_v2.py::test_street_style_within_6pp_of_target_in_mixed_field)
    out = []
    for gi, grp in enumerate(grid.TABLES):
        ss = np.random.SeedSequence(gi).spawn(6)
        agents = [PersonaAgent(PRESETS_V2[n], np.random.default_rng(s)) for n, s in zip(grp, ss)]
        out += [(n, st.wtsd, st.vpip, st.fold_river) for n, st in zip(grp, measure_session(agents, hands, seed=50 + gi))]
    return out


def test_default_seed_offset_replays_the_mixed_field_test_seeds():
    # #736: offset 0 (the CLI default) must be the test's seeds, another offset must not be
    want = _test_seeds_replay(300)
    for raw in (grid.measure(PRESETS_V2, 300), grid.measure(PRESETS_V2, 300, seed_offset=0)):
        assert [(s["type"], s["wtsd"], s["vpip"], s["fold_river"]) for s in raw["seats"]] == want
    other = grid.measure(PRESETS_V2, 300, seed_offset=1)
    assert [(s["type"], s["wtsd"], s["vpip"], s["fold_river"]) for s in other["seats"]] != want
    assert repr(grid.evaluate(PRESETS_V2, 300)) == repr(grid.judge(PRESETS_V2, grid.measure(PRESETS_V2, 300)))  # nan-safe


def test_pool_averages_seats_and_sums_cells():
    a, b = grid.measure(PRESETS_V2, 300), grid.measure(PRESETS_V2, 300, seed_offset=1)
    assert repr(grid.judge(PRESETS_V2, grid.pool([a]))) == repr(grid.judge(PRESETS_V2, a))  # nan-safe at 300 hands
    m = grid.pool([a, b])
    assert m["seats"][0]["vpip"] == pytest.approx((a["seats"][0]["vpip"] + b["seats"][0]["vpip"]) / 2)
    n = next(iter(grid.CELLS))
    assert all(m["opp"][n][k] == a["opp"][n][k] + b["opp"][n][k] for k in m["opp"][n])
