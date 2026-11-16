"""#711: visit-count quantiles in the E3 result (additive fields only)."""
from types import SimpleNamespace

from stalker import train_jobs as T
from stalker.e3.mccfr import E3MCCFR, visit_quantiles


def test_quantiles_of_hand_made_visits():
    m = SimpleNamespace(visits={f"k{i}": v for i, v in enumerate([1, 5, 9, 10, 20, 30, 40, 50, 60, 100])})
    assert visit_quantiles(m) == {"keys": 10, "under10": 3, "p10": 1, "p25": 9, "p50": 20, "p75": 40, "p90": 60}
    assert visit_quantiles(m, {"k0", "k9"})["keys"] == 2


def test_empty_visits_gives_only_keys():
    assert visit_quantiles(SimpleNamespace(visits={})) == {"keys": 0}


def test_e3_tp_result_has_quantiles_and_keeps_old_fields(tmp_path, monkeypatch):
    for name in ("E3_LBR_HANDS", "E3_FIELD_HANDS"):
        monkeypatch.setattr(T, name, 2)
    res = T._e3_tp(3, 1, tmp_path, tier="beginner", name="x", lbr_hands=4)
    assert 0 < res["visit_quantiles"]["keys"] <= res["infosets"]
    assert "visit_quantiles_by_players" not in res
    assert {"infosets", "lbr", "regret_sha256", "eval_config_sha256"} <= set(res)


def test_player_mix_adds_by_players(tmp_path):
    m = E3MCCFR(1, 3, 3, key_variant="c1", player_mix=(2, 3))
    m.iterate(6)
    out = T._e3_visit_quantiles(m)
    assert set(out["visit_quantiles_by_players"]) <= {"2", "3"} and out["visit_quantiles_by_players"]


def test_summarize_adds_p50_only_when_all_seeds_have_it(tmp_path):
    import json
    base = {"iters": 1, "iters_per_s": 1.0, "lbr": {"lbr_bb": 1.0}}
    for s, vq in ((1, {"p50": 7}), (2, {"p50": 9})):
        (tmp_path / f"e3-x-seed{s}.json").write_text(json.dumps({**base, "seed": s, "visit_quantiles": vq}), encoding="utf-8")
    assert T.summarize("e3-x", tmp_path)["visit_p50_by_seed"] == [7, 9]
    (tmp_path / "e3-x-seed2.json").write_text(json.dumps({**base, "seed": 2}), encoding="utf-8")
    assert "visit_p50_by_seed" not in T.summarize("e3-x", tmp_path)


def test_key_cells_bubble_run_names_one_cell_and_one_player_count():
    from stalker.e3 import tp_key as K
    kw = dict(k=K.TIER_K["beginner"], depth=K.TIER_DEPTH["beginner"], key_variant="c1", stacks="bubble:random",
              stack_preset="9max_sng_503020", stack_remaining=4, stack_level=1, stage="b")
    m = E3MCCFR(1, n=4, **kw)
    m.iterate(20)
    cells = T._e3_key_cells(m)
    assert list(cells["t"]) == ["b0"] and list(cells["n"]) == ["4"]
    assert cells["n"]["4"] <= len(m.visits)


def test_key_cells_cash_mix_has_no_t_and_one_n_per_player_count():
    m = E3MCCFR(1, 3, 3, key_variant="c1", player_mix=(2, 3))
    m.iterate(30)
    cells = T._e3_key_cells(m)
    assert cells["t"] == {} and set(cells["n"]) == {"2", "3"}


def test_key_cells_non_c1_is_empty_and_survives_blob_strip():
    from harness.cloud.launcher import SUMMARY_BLOB_CHARS, _strip_blobs
    m = E3MCCFR(1, 3, 3)
    m.iterate(3)
    assert T._e3_key_cells(m) == {"t": {}, "n": {}}
    m = E3MCCFR(1, 3, 3, key_variant="c1", player_mix=(2, 3))
    m.iterate(10)
    cells = T._e3_key_cells(m)
    import json
    assert len(json.dumps(cells)) <= SUMMARY_BLOB_CHARS
    assert _strip_blobs({"key_cells": cells}) == {"key_cells": cells}


def test_e3_tp_result_carries_key_cells(tmp_path, monkeypatch):
    for name in ("E3_LBR_HANDS", "E3_FIELD_HANDS"):
        monkeypatch.setattr(T, name, 2)
    res = T._e3_tp(3, 1, tmp_path, tier="beginner", name="x", lbr_hands=4)
    assert res["key_cells"] == {"t": {}, "n": {}}
