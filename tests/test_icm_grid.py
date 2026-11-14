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
