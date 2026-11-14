import json

import pytest

from stalker.tools.icm_grid import MD_NOTE, main, run_grid

PRESETS = ["6max_sng_topheavy", "9max_sng_503020"]
GAMES = 3


def _cli(tmp_path, name, *extra):
    out, md = tmp_path / f"{name}.json", tmp_path / f"{name}.md"
    main(["--presets", ",".join(PRESETS), "--remaining", "2,3,7", "--profiles", "even,skewed", "--games", str(GAMES),
          "--seed", "5", "--out", str(out), "--md", str(md), *extra])
    return out, md


def test_same_args_give_identical_json_bytes(tmp_path):
    a, _ = _cli(tmp_path, "a")
    b, _ = _cli(tmp_path, "b")
    assert a.read_bytes() == b.read_bytes()
    d = json.loads(a.read_bytes())
    assert (d["schema_version"], d["seed"], d["games"]) == (1, 5, GAMES)


def test_cells_are_the_valid_combinations_and_skipped_only_the_invalid_ones(tmp_path):
    out, md = _cli(tmp_path, "g")
    d = json.loads(out.read_text(encoding="utf-8"))
    # 6-max: remaining 2,3 valid, 7 invalid; 9-max: 2,3,7 valid; x2 profiles
    assert len(d["cells"]) == (2 + 3) * 2
    assert {(s["preset"], s["remaining"]) for s in d["skipped"]} == {("6max_sng_topheavy", 7)}
    assert len(d["skipped"]) == 2 and all("players=6" in s["reason"] for s in d["skipped"])
    for c in d["cells"]:
        raw = c["calibrate"]
        assert c["max_abs_diff"] == pytest.approx(max(abs(x) for x in raw["diff"]))
        assert c["max_abs_diff_rel"] == pytest.approx(c["max_abs_diff"] / raw["prize_pool"])
        assert c["max_abs_z"] >= 0
    rows = [ln for ln in md.read_text(encoding="utf-8").splitlines() if ln.startswith("|")]
    assert md.read_text(encoding="utf-8").splitlines()[0] == MD_NOTE
    assert len(rows) == len(d["cells"]) + 2  # header + separator


def test_remaining_below_two_is_skipped():
    g = run_grid(["6max_sng_topheavy"], [1], ["even"], GAMES, 0)
    assert g["cells"] == [] and len(g["skipped"]) == 1 and "< 2" in g["skipped"][0]["reason"]


def test_dropping_a_profile_leaves_common_cells_unchanged():
    full = run_grid(PRESETS, [2, 3], ["even", "random", "skewed"], GAMES, 9)
    part = run_grid(PRESETS, [2, 3], ["even", "skewed"], GAMES, 9)
    key = lambda c: (c["preset"], c["remaining"], c["profile"])
    full_by_key = {key(c): c["calibrate"] for c in full["cells"]}
    assert len(part["cells"]) == 8
    for c in part["cells"]:
        assert c["calibrate"] == full_by_key[key(c)]


def test_even_cells_pay_out_the_whole_pool():
    g = run_grid(PRESETS, [2, 3], ["even"], GAMES, 1)
    for c in g["cells"]:
        raw = c["calibrate"]
        assert sum(raw["sim_prize_mean"]) == pytest.approx(raw["prize_pool"], abs=1e-9)


def test_bad_profile_exits_with_a_message(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--presets", "6max_sng_topheavy", "--remaining", "2", "--profiles", "flat", "--games", "1"])
    assert e.value.code == 2 and "flat" in capsys.readouterr().err


def test_default_agents_output_is_the_pre_option_computation(tmp_path):
    import numpy as np

    from stalker.tools.icm_calibration import calibrate
    from stalker.tools.icm_grid import cell_seed
    from stalker.tournament.config import load_preset
    from stalker.tournament.start_state import make_start_state

    a, _ = _cli(tmp_path, "default")
    b, _ = _cli(tmp_path, "random", "--agents", "random")
    assert a.read_bytes() == b.read_bytes()
    d = json.loads(a.read_bytes())
    assert "agents" not in d
    c = d["cells"][0]
    config = load_preset(c["preset"])
    rng = np.random.default_rng(cell_seed(5, c["preset"], c["remaining"], c["profile"]))
    ss = make_start_state(config, rng, c["remaining"], c["profile"], 0)
    want = calibrate(config, ss, None, GAMES, rng)
    assert c["calibrate"] == json.loads(json.dumps(want))


def test_persona_agents_change_every_cell_and_are_recorded():
    base = run_grid(["6max_sng_topheavy"], [3, 4], ["even", "skewed"], 10, 3)
    tag = run_grid(["6max_sng_topheavy"], [3, 4], ["even", "skewed"], 10, 3, agents="persona:tag")
    assert tag["agents"] == "persona:tag" and "agents" not in base
    assert len(tag["cells"]) == len(base["cells"]) == 4
    for b, t in zip(base["cells"], tag["cells"]):
        assert (b["preset"], b["remaining"], b["profile"]) == (t["preset"], t["remaining"], t["profile"])
        assert b["calibrate"]["sim_prize_mean"] != t["calibrate"]["sim_prize_mean"]


def test_bad_agents_spec_exits_with_a_message(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--presets", "6max_sng_topheavy", "--remaining", "2", "--games", "1", "--agents", "persona:bogus"])
    assert e.value.code == 2 and "bogus" in capsys.readouterr().err


def test_new_options_at_defaults_keep_output_bytes_and_schema(tmp_path):
    """#858: --level-index 0 --layouts 1 is the pre-option computation, byte for byte."""
    a, _ = _cli(tmp_path, "plain")
    b, _ = _cli(tmp_path, "explicit", "--level-index", "0", "--layouts", "1")
    assert a.read_bytes() == b.read_bytes()
    d = json.loads(a.read_bytes())
    assert d["schema_version"] == 1 and "layouts" not in d and "level_index" not in d["cells"][0]


def test_two_layouts_record_two_different_stack_sets_per_cell():
    g = run_grid(["9max_sng_503020"], [4], ["skewed"], 4, 2, layouts=2)
    assert g["schema_version"] == 2 and g["layouts"] == 2 and g["level_indexes"] == [0]
    assert [c["layout"] for c in g["cells"]] == [0, 1]
    s0, s1 = (c["calibrate"] for c in g["cells"])
    assert s0["stacks"] != s1["stacks"]


def test_level_index_cells_are_recorded_per_level_and_layout0_matches_v1_seed():
    g = run_grid(["9max_sng_503020"], [3], ["random"], 4, 2, level_indexes=[0, 3])
    assert [(c["level_index"], c["layout"]) for c in g["cells"]] == [(0, 0), (3, 0)]
    v1 = run_grid(["9max_sng_503020"], [3], ["random"], 4, 2)
    assert g["cells"][0]["calibrate"] == v1["cells"][0]["calibrate"]
    assert g["cells"][1]["calibrate"] != g["cells"][0]["calibrate"]


def test_dropping_a_level_or_layout_leaves_the_others_unchanged():
    full = run_grid(["9max_sng_503020"], [3], ["skewed"], 3, 4, level_indexes=[0, 3], layouts=3)
    part = run_grid(["9max_sng_503020"], [3], ["skewed"], 3, 4, level_indexes=[3], layouts=2)
    by = {(c["level_index"], c["layout"]): c["calibrate"] for c in full["cells"]}
    assert [(c["level_index"], c["layout"]) for c in part["cells"]] == [(3, 0), (3, 1)]
    for c in part["cells"]:
        assert c["calibrate"] == by[(c["level_index"], c["layout"])]


def test_markdown_has_level_and_layout_columns_in_v2():
    from stalker.tools.icm_grid import to_markdown
    md = to_markdown(run_grid(["9max_sng_503020"], [3], ["even"], 2, 0, level_indexes=[0, 2]))
    assert "| level | layout |" in md and md.count("\n| 9max") == 2


def test_bad_level_index_and_layouts_exit_with_a_message(capsys):
    for extra, word in ((["--level-index", "99"], "99"), (["--layouts", "0"], "layouts")):
        with pytest.raises(SystemExit) as e:
            main(["--presets", "9max_sng_503020", "--remaining", "3", "--games", "1", *extra])
        assert e.value.code == 2 and word in capsys.readouterr().err


# ---- --lambda-grid (#866, ADR 0026 CI selection procedure) ----
from stalker.tools.icm_grid import DEFAULT_LAMBDA_GRID, select_lambda, summarize_lambdas  # noqa: E402


def _row(lam, bs, bm, ps):
    return {"lambda": lam, "bubble_significant": bs, "bubble_mean_rel": bm, "in_prize_significant": ps}


def test_select_picks_fewest_significant_bubble_cells():
    rows = [_row(0.0, 4, 0.05, 1), _row(0.1, 2, 0.04, 1), _row(0.2, 1, 0.03, 1)]
    assert select_lambda(rows) == 0.2


def test_select_ties_go_to_smaller_mean_then_smaller_lambda():
    assert select_lambda([_row(0.0, 3, 0.05, 0), _row(0.1, 1, 0.04, 0), _row(0.2, 1, 0.03, 0)]) == 0.2
    assert select_lambda([_row(0.0, 3, 0.05, 0), _row(0.1, 1, 0.03, 0), _row(0.2, 1, 0.03, 0)]) == 0.1


def test_select_skips_lambdas_that_add_in_prize_significant_cells():
    rows = [_row(0.0, 4, 0.05, 1), _row(0.1, 3, 0.04, 1), _row(0.2, 0, 0.01, 2)]
    assert select_lambda(rows) == 0.1


def test_select_keeps_zero_when_nothing_reduces_bubble_significance():
    # all worse, and ties on (i) even with a smaller (ii) do not beat lambda=0
    assert select_lambda([_row(0.0, 2, 0.05, 0), _row(0.1, 3, 0.06, 0), _row(0.2, 4, 0.07, 0)]) == 0.0
    assert select_lambda([_row(0.0, 2, 0.05, 0), _row(0.1, 2, 0.01, 0)]) == 0.0
    # the only improving lambda is excluded by in-prize worsening
    assert select_lambda([_row(0.0, 2, 0.05, 0), _row(0.1, 0, 0.01, 1)]) == 0.0


def _lam_grid(lambdas, **kw):
    return run_grid(["9max_sng_503020"], [3, 4], ["even", "skewed"], GAMES, 3, lambda_grid=lambdas, **kw)


def test_lambda_grid_scores_the_same_simulation_for_any_list():
    a, b = _lam_grid([0, 0.1]), _lam_grid([0, 0.5, 0.2])
    for ca, cb in zip(a["cells"], b["cells"], strict=True):
        assert json.dumps(ca["calibrate"]["sim_prize_mean"]) == json.dumps(cb["calibrate"]["sim_prize_mean"])
        assert ca["lambda_metrics"][0] == cb["lambda_metrics"][0]  # lambda=0 is first in both


def test_lambda_grid_output_shape_and_zones():
    g = _lam_grid(list(DEFAULT_LAMBDA_GRID), layouts=1)
    assert g["schema_version"] == 3 and g["lambda_grid"] == list(DEFAULT_LAMBDA_GRID)
    zones = {c["remaining"]: c["zone"] for c in g["cells"]}
    assert zones == {3: "in_prize", 4: "bubble"}  # 9max_sng_503020 pays 3
    for c in g["cells"]:
        assert [m["lambda"] for m in c["lambda_metrics"]] == list(DEFAULT_LAMBDA_GRID)
        assert c["lambda_metrics"][0]["max_abs_diff_rel"] == pytest.approx(c["max_abs_diff_rel"])
        assert c["lambda_metrics"][0]["max_abs_z"] == pytest.approx(c["max_abs_z"])
        if c["zone"] == "in_prize":  # lambda only acts on the bubble
            assert len({m["max_abs_diff_rel"] for m in c["lambda_metrics"]}) == 1
    s = g["lambda_summary"]
    assert [r["bubble_cells"] for r in s] == [2] * 6 and [r["in_prize_cells"] for r in s] == [2] * 6
    assert g["selected_lambda"] == select_lambda(s) == select_lambda(summarize_lambdas(g["cells"], g["lambda_grid"]))


def test_lambda_grid_without_zero_or_out_of_range_is_an_error():
    with pytest.raises(ValueError, match="include 0"):
        _lam_grid([0.1, 0.2])
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        _lam_grid([0, 1.5])
    with pytest.raises(ValueError, match="duplicates"):
        _lam_grid([0, 0.1, 0.1])


def test_no_lambda_flag_output_is_unchanged_and_composes_with_layouts(tmp_path):
    plain = run_grid(["9max_sng_503020"], [4], ["even"], GAMES, 3)
    assert plain["schema_version"] == 1 and "lambda_grid" not in plain
    assert all("lambda_metrics" not in c for c in plain["cells"])
    both = run_grid(["9max_sng_503020"], [4], ["even"], GAMES, 3, level_indexes=[0, 1], layouts=2,
                    lambda_grid=[0, 0.2])
    assert len(both["cells"]) == 4 and all({"level_index", "layout", "zone"} <= c.keys() for c in both["cells"])
    out, md = tmp_path / "l.json", tmp_path / "l.md"
    assert main(["--presets", "9max_sng_503020", "--remaining", "4", "--profiles", "even", "--games", str(GAMES),
                 "--lambda-grid", "--out", str(out), "--md", str(md)]) == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["lambda_grid"] == list(DEFAULT_LAMBDA_GRID) and "selected λ" in md.read_text(encoding="utf-8")


def test_lambda_grid_cli_rejects_grid_without_zero(tmp_path):
    with pytest.raises(SystemExit) as e:
        main(["--presets", "9max_sng_503020", "--remaining", "4", "--games", "1", "--lambda-grid", "0.1,0.2"])
    assert e.value.code == 2


def test_old_levels_json_still_reads_with_the_v2_reader():
    d = json.loads(open("docs/research/data/icm-bias-levels-2026-11-14-random.json", encoding="utf-8").read())
    assert d["schema_version"] == 2 and "lambda_grid" not in d
    from stalker.tools.icm_grid import to_markdown
    assert "selected" not in to_markdown(d)
