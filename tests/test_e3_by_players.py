"""#534: `e3_evaluate` reports LBR and the field per table size for player-mix models only."""
import pytest

from stalker import train_jobs as T
from stalker.e3.mccfr import E3MCCFR

TOP = {"field", "field_seconds", "infosets", "coverage", "lbr", "lbr_average", "lbr_offmenu", "lbr_seconds",
       "policy_sha256"}


@pytest.fixture
def small(monkeypatch):
    for name in ("E3_LBR_HANDS", "E3_FIELD_HANDS", "E3_BY_PLAYERS_LBR_HANDS", "E3_BY_PLAYERS_FIELD_HANDS"):
        monkeypatch.setattr(T, name, 2)


def test_model_without_player_mix_keeps_its_output(small, monkeypatch):
    m = E3MCCFR(1, 5, 3, "basic")
    m.iterate(2)
    before = T.e3_evaluate(m, 0)
    monkeypatch.setattr(T, "_by_players", lambda *a: pytest.fail("no player_mix -> no by_players"))
    out = T.e3_evaluate(m, 0)
    assert set(out) == TOP and out["field"] is None
    assert {k: v for k, v in out.items() if not k.endswith("seconds")} == \
        {k: v for k, v in before.items() if not k.endswith("seconds")}


def test_player_mix_model_reports_each_dealt_table_size(small):
    m = E3MCCFR(1, 5, 3, "basic", player_mix=(2, 3))
    m.iterate(2)
    out = T.e3_evaluate(m, 0)
    assert set(out) == TOP | {"by_players"} and set(out["by_players"]) == {"2", "3"}
    for n, row in out["by_players"].items():
        assert set(row) == {"lbr", "lbr_average", "field", "seconds"} and row["seconds"] >= 0
        assert len(row["lbr"]["by_seat"]) == int(n) and row["lbr"]["hands"] == 2 and "lbr_bb" in row["lbr_average"]
        f = row["field"]
        assert f["version"] == 3 and f["deals"] == 2 and f["worst"]["name"]
        assert all(len(c["opponents"]) == int(n) - 1 for c in f["configs"])
    # 3 is the model's own n: its LBR is the top-level one (a 3-player model has no 6-max field to reuse)
    assert out["by_players"]["3"]["lbr"] == out["lbr"] and out["field"] is None


def test_six_seat_entry_reuses_the_top_level_numbers(small, monkeypatch):
    m = E3MCCFR(1, 5, 6, "basic", player_mix=(5, 6))
    m.iterate(1)
    monkeypatch.setattr("referee.e3.field.evaluate", lambda *a, **kw: {"players": kw.get("players", 6)})
    out = T.e3_evaluate(m, 0)
    assert out["by_players"]["6"]["field"] is out["field"] and out["by_players"]["6"]["lbr"] == out["lbr"]
    assert out["by_players"]["5"]["field"] == {"players": 5}
