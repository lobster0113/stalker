"""#534: `e3_evaluate` reports LBR and the field per table size for player-mix models only."""
import pytest

from stalker import train_jobs as T
from stalker.e3.mccfr import E3MCCFR

TOP = {"field", "field_seconds", "infosets", "coverage", "lbr", "lbr_average", "lbr_offmenu", "lbr_seconds",
       "policy_sha256"}
MIX_TOP = {"by_players", "by_players_counted_from", "by_players_shared_keys"}   # #534, #535


@pytest.fixture
def small(monkeypatch):
    for name in ("E3_LBR_HANDS", "E3_FIELD_HANDS", "E3_BY_PLAYERS_LBR_HANDS", "E3_BY_PLAYERS_FIELD_HANDS"):
        monkeypatch.setattr(T, name, 2)
    monkeypatch.setattr(T, "E3_BY_PLAYERS_LBR_HANDS_BY_N", {})


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
    assert set(out) == TOP | MIX_TOP and set(out["by_players"]) == {"2", "3"}
    for n, row in out["by_players"].items():
        assert set(row) == {"lbr", "lbr_average", "field", "seconds", "lbr_hands", "hands", "visits",
                            "keys"} and row["seconds"] >= 0
        assert len(row["lbr"]["by_seat"]) == int(n) and row["lbr"]["hands"] == row["lbr_hands"] == 2 and "lbr_bb" in row["lbr_average"]
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


def test_lbr_hands_per_table_size(monkeypatch):
    """#556: 2-3 seats get 2000 LBR hands (600 left se ~ cross-seed sd, #548), 4-5 keep 600; rows say which."""
    for name in ("E3_LBR_HANDS", "E3_FIELD_HANDS", "E3_BY_PLAYERS_FIELD_HANDS"):
        monkeypatch.setattr(T, name, 2)
    calls = []

    def fake_lbr(pol, hands, seed, k, n, depth, **kw):
        calls.append((n, hands))
        return {"lbr_bb": 0.0, "hands": hands, "by_seat": [0.0] * n}

    monkeypatch.setattr("referee.e3.lbr.exploitability_lb", fake_lbr)
    monkeypatch.setattr("referee.e3.field.evaluate", lambda *a, **kw: {"players": kw.get("players", 6)})
    m = E3MCCFR(1, 5, 6, "basic", player_mix=(2, 3, 4, 5, 6))
    m.iterate(1)
    out = T.e3_evaluate(m, 0)
    by_n = {n: {h for nn, h in calls if nn == n} for n in (2, 3, 4, 5)}
    assert by_n == {2: {2000}, 3: {2000}, 4: {600}, 5: {600}}
    assert {n: row["lbr_hands"] for n, row in out["by_players"].items()} == \
        {"2": 2000, "3": 2000, "4": 600, "5": 600, "6": 2}   # 6 is the model's own size: the top-level LBR
