"""scripts/persona_cell_grid.py judges a point with the same guards and values as the mixed-field test (#730)."""
import importlib.util
import pathlib

import numpy as np
import pytest

from stalker.agents.persona import PRESETS_V2, PersonaAgent
from stalker.agents.persona_stats import measure_session
from tests.test_persona_v2 import MIXED_OFFSETS, SEAT_KEYS, _mixed_field_judgment, _mixed_seats

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
    # ADR 0023: the script's judge(pool(4 seed sets)) and the test's own 4-set seat mean must agree on the same raws
    raws = [grid.measure(PRESETS_V2, seed_offset=k) for k in MIXED_OFFSETS]
    res = grid.judge(PRESETS_V2, grid.pool(raws))
    assert res["passed"], res["violations"]
    runs = [[(s["type"], {k: s[k] for k in SEAT_KEYS}) for s in r["seats"]] for r in raws]
    bad, _, _, err, river = _mixed_field_judgment(runs)
    assert not bad, bad
    assert (res["turn_err"], res["river_err"]) == (pytest.approx(err, abs=5e-5), pytest.approx(river, abs=5e-5))


def test_test_seed_sets_replay_the_script_offsets():
    # the test's _mixed_seats(k) and the script's measure(seed_offset=k) play the same hands, so the slow check above
    # can feed one measurement to both judgments
    for k in MIXED_OFFSETS:
        want = [(n, st["wtsd"], st["vpip"], st["fold_river"]) for n, st in _mixed_seats(k, 300)]
        assert [(s["type"], s["wtsd"], s["vpip"], s["fold_river"]) for s in grid.measure(PRESETS_V2, 300, seed_offset=k)["seats"]] == want, k


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
