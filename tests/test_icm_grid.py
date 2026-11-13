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
