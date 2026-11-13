"""#611: web policy table hit-rate tool."""
import json
from pathlib import Path

import pytest

from stalker.tools import web_hit_rate as H

K, DEPTH, N3 = 11, "full", 3
MID3 = Path("web/app/policy/mid-3.json")


@pytest.fixture(scope="module")
def _mid3_once():
    pol, doc = H.load_policy(MID3)
    return MID3.read_bytes(), pol, doc, H.coarse_tables(pol)


@pytest.fixture
def mid3_shared(_mid3_once, monkeypatch):
    """mid-3.json is read, and its backoff tables built, once per module instead of once per `measure` (#826: the
    tables are most of a short run's time). `measure` adds `l1_extra` rows into the tables, so each call gets a copy;
    the policy and header are only read."""
    raw, pol, doc, tables = _mid3_once
    load, build = H.load_policy, H.coarse_tables
    monkeypatch.setattr(H, "load_policy", lambda path: (pol, doc) if Path(path).read_bytes() == raw else load(path))
    monkeypatch.setattr(H, "coarse_tables", lambda policy: [{ck: dict(by_m) for ck, by_m in t.items()} for t in tables]
                        if policy is pol else build(policy))


class Spy(dict):
    """Records the keys looked up; the first lookup is the first actor's real key."""
    def __init__(self, *a):
        super().__init__(*a)
        self.asked = []

    def get(self, k, d=None):
        self.asked.append(k)
        return super().get(k, d)


def _first_key():
    spy = Spy()
    H.measure(spy, N3, K, DEPTH, 1, 5)
    return spy.asked[0]


def _totals(r):
    return sum(c["decisions"] for c in r["by_street"].values()), sum(c["hits"] for c in r["by_street"].values())


def test_empty_policy_never_hits_and_same_seed_same_output():
    a = H.measure({}, N3, K, DEPTH, 3, 5)
    assert a == H.measure({}, N3, K, DEPTH, 3, 5)
    n, hits = _totals(a)
    assert n > 0 and hits == 0
    assert sum(c["decisions"] for c in a["by_kind"].values()) == n


def test_one_key_hits_on_its_street_only_and_min_visits_filters():
    key = _first_key()
    # the row length must match the legal actions: try widths until the key hits
    for width in (2, 3, 4, 5, 6, 7, 8):
        pol = {key: [1.0 / width] * width}
        r = H.measure(pol, N3, K, DEPTH, 1, 5, visits={key: 3})
        if r["by_street"]["0"]["hits"]:
            break
    assert r["by_street"]["0"]["hits"] == 1  # the seeded hand reaches this key once (counted by running it)
    assert all(r["by_street"][s]["hits"] == 0 for s in "123")
    mv = r["by_min_visits"]
    assert mv["2"]["by_street"]["0"]["hits"] == 1 and mv["5"]["by_street"]["0"]["hits"] == 0
    assert mv["0"]["by_street"]["0"]["decisions"] == r["by_street"]["0"]["decisions"]


def test_load_policy_divides_by_q(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"q": 255, "policy": {"k": [255, 0]}}), encoding="utf-8")
    assert H.load_policy(p)[0] == {"k": [1.0, 0.0]}


def test_main_prints_json_for_a_small_policy_file(tmp_path, capsys):
    p = tmp_path / "t-3.json"
    p.write_text(json.dumps({"q": 255, "players": N3, "k": K, "depth": DEPTH, "policy": {}}), encoding="utf-8")
    assert H.main([str(p), "--hands", "1"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["players"] == N3 and out["file"] == "t-3.json" and out["by_street"]["0"]["hits"] == 0


# --- #618: the page's rules (menu, stacks) and the coarse-key backoff ---

REAL = {"menu": "real", "raise_cap": None}


def test_rules_of_reads_the_menu_as_the_page_menuOf():
    assert H.rules_of({}) == {"menu": "v1", "raise_cap": 3}
    assert H.rules_of({"menu": "real", "raise_cap": None}) == REAL


def test_hands_are_played_on_the_tables_menu_at_100bb_as_the_page():
    spy = Spy()
    H.measure(spy, N3, K, DEPTH, 1, 5, rules=REAL)
    first = spy.asked[0].split("|")
    assert first[-2].startswith("fcr2")   # the real menu's sized opens, not v1's single "r"
    assert "s6:6" in first                # page hands start at 100BB for everyone (tpgto.js STACK)


def test_main_plays_the_files_menu(tmp_path, monkeypatch):
    seen = {}
    real_measure = H.measure

    def spy_measure(*a, **kw):
        seen.update(kw)
        return real_measure(*a, **kw)

    monkeypatch.setattr(H, "measure", spy_measure)
    p = tmp_path / "t-3.json"
    p.write_text(json.dumps({"q": 255, "players": N3, "k": K, "depth": DEPTH, "menu": "real", "raise_cap": None,
                             "policy": {}}), encoding="utf-8")
    assert H.main([str(p), "--hands", "1"]) == 0
    assert seen["rules"] == REAL


def test_coarse_key_levels():
    post = "BTN|n3|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e5|o1v1k0"
    assert H.coarse_key(post, 0) == post
    assert H.coarse_key(post, 1) == "BTN|n3|1|1|0|2|0|0|tc0|s*|u10|hn|go|ka|e5"
    assert H.coarse_key(post, 2) == "BTN|n3|1|1|0|2|0|*|tc0|s*|*|*|*|ka|e5"
    pre = "SB|n3|0|2|1|0|3|0|tc0|s7:75|u11|hb|fcr25rr35r4r5a|e2"
    assert H.coarse_key(pre, 2) == "SB|n3|0|2|1|0|3|*|tc0|s*|*|*|fcr25rr35r4r5a|e2"
    call = "call|0|1|1|fc|e0"
    assert H.coarse_key(call, 1) == call and H.coarse_key(call, 2) == "call|0|*|1|fc|e0"
    pro = "p|BTN|n6|1|1|0|2|0|3|tc0|s7:7|u0|hn|go|ka|f-|e5|n2|o1v1k0"
    assert H.coarse_key(pro, 2) == "p|BTN|n6|1|1|0|2|0|*|tc0|s*|*|*|*|ka|f-|e5|n2"
    basic = "b|n3|late|1|1|0|2|tc0|s7:7|u10|hn|ka|e3|o1"
    assert H.coarse_key(basic, 2) == "b|n3|late|1|1|0|2|tc0|s*|*|*|ka|e3"


def test_a_missing_key_hits_at_l1_with_the_mean_of_the_rows_it_shares_with():
    a = "BTN|n3|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e5|o1v1k0"
    b = "BTN|n3|1|1|0|2|0|0|tc0|s7:7|u10|hn|go|ka|e5|o1v1k0"
    third = "BTN|n3|1|1|0|2|0|0|tc0|s5:5|u10|hn|go|ka|e5|o1v1k0"   # same L1 key, not in the table
    other_len = "BTN|n3|1|1|0|2|0|0|tc0|s6:6|u10|hn|go|ka|e5|o1v1k0"
    pol = {a: [1.0, 0.0], b: [0.5, 0.5], other_len: [1.0, 0.0, 0.0]}
    tabs = H.coarse_tables(pol)
    assert tabs[0][H.coarse_key(third, 1)][2] == [0.75, 0.25]   # rows of another length are kept apart
    assert tabs[0][H.coarse_key(third, 1)][3] == [1.0, 0.0, 0.0]
    assert H.backoff_level(pol, tabs, a, 2) == 0
    assert H.backoff_level(pol, tabs, third, 2) == 1
    assert H.backoff_level(pol, tabs, third, 4) == 4   # no row of that length at any level: uniform
    l2_only = "BTN|n3|1|1|0|2|0|4|tc0|s5:5|u01|ha|gm|ka|e5|o-v-k2"
    assert H.backoff_level(pol, tabs, l2_only, 2) == 2


def test_backoff_counts_are_deterministic_and_off_is_the_old_output():
    key = _first_key()
    pol = {key: [0.5, 0.5]}
    off = H.measure(pol, N3, K, DEPTH, 3, 5)
    on = H.measure(pol, N3, K, DEPTH, 3, 5, backoff=True)
    assert on == H.measure(pol, N3, K, DEPTH, 3, 5, backoff=True)
    assert {k: v for k, v in on.items() if k != "by_backoff"} == off and "by_backoff" not in off
    bb = on["by_backoff"]
    assert bb["levels"] == ["exact", "L1", "L2", "L3", "uniform"]
    for st, c in bb["by_street"].items():
        assert c["decisions"] == off["by_street"][st]["decisions"]
        assert c["exact"] == off["by_street"][st]["hits"]
        assert c["exact"] + c["L1"] + c["L2"] + c["L3"] + c["uniform"] == c["decisions"]
    # #819: every by_backoff cell carries the Wilson interval of its uniform share, null at 0 decisions
    cells = [*bb["by_street"].values(), *bb["by_kind"].values()]
    assert any(c["decisions"] == 0 for c in cells) and any(c["decisions"] > 0 for c in cells)
    for c in cells:
        assert c["uniform_ci95"] == H.uniform_ci95(c)
        assert (c["uniform_ci95"] is None) == (c["decisions"] == 0)


# --- #620: legacy (pre-c1) key tables ---

def _asked(variant, rules=None):
    spy = Spy()
    H.measure(spy, N3, K, DEPTH, 1, 5, variant=variant, rules=rules)
    return spy.asked


def test_legacy_variant_looks_up_the_pre_c1_key_the_page_asks():
    legacy, c1 = _asked("")[0], _asked("c1")[0]
    assert "|n" not in legacy   # bare-number fields, no position/players names
    assert "|n" in c1 and legacy != c1


def test_legacy_table_hits_by_exact_counts_and_c1_table_of_same_hand_does_not():
    legacy = _asked("")[0]
    for width in (2, 3, 4, 5, 6):
        r = H.measure({legacy: [1.0 / width] * width}, N3, K, DEPTH, 1, 5, variant="")
        if r["by_street"]["0"]["hits"]:
            break
    assert r["by_street"]["0"]["hits"] == 1 and _totals(r)[1] == 1
    assert r["by_kind"]["call"]["decisions"] == 1   # the call-or-fold key is the same in both layouts
    assert _totals(H.measure({legacy: [0.5, 0.5]}, N3, K, DEPTH, 1, 5, variant="c1"))[1] == 0


def test_variant_of_reads_header_then_first_key_and_the_flag_wins():
    assert H.variant_of({}, {"key_variant": "c1"}) == "c1"
    assert H.variant_of({"0|0|1|1|0|2|0|fcra|e0": [1.0]}, {}) == ""
    assert H.variant_of({"BTN|n3|0|e1": [1.0]}, {}) == "c1"
    assert H.variant_of({"call|0|1|1|fc|e0": [1.0], "0|0|1|1|0|2|0|fcra|e0": [1.0]}, {}) == ""
    assert H.variant_of({"call|0|1|1|fc|e0": [1.0]}, {}) == "c1"
    assert H.variant_of({}, {}) == "c1"
    assert H.variant_of({"call|0|1|1|fc|e0": [1.0]}, {}, "legacy") == ""


def test_main_reads_a_legacy_file_as_legacy(tmp_path, capsys):
    p = tmp_path / "t-3.json"
    p.write_text(json.dumps({"q": 255, "players": N3, "k": K, "depth": DEPTH,
                             "policy": {"0|0|1|1|0|2|0|fcra|e0": [255, 0]}}), encoding="utf-8")
    assert H.main([str(p), "--hands", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["variant"] == "legacy"
    try:
        H.main([str(p), "--backoff"])
    except SystemExit as e:
        assert "legacy" in str(e)
    else:
        raise AssertionError("--backoff on a legacy table must stop")


# --- #635: play by the page's backoff rule ---

def _mid3(play):
    from pathlib import Path
    pol, doc = H.load_policy(Path("web/app/policy/mid-3.json"))
    return H.measure(pol, doc["players"], doc["k"], doc["depth"], 20, 5, rules=H.rules_of(doc),
                     variant=H.variant_of(pol, doc), play_backoff=play, backoff=True)


def _levels(r):
    keys = ("decisions", "exact", "L1", "L2", "L3", "uniform")
    return {st: {k: c[k] for k in keys} for st, c in r["by_backoff"]["by_street"].items()}


def test_play_backoff_levels_are_exact_and_the_trajectory_differs_from_uniform_play(mid3_shared):
    uni, bo = _mid3(False), _mid3(True)
    assert "play" not in uni and uni["schema_version"] == 2
    assert bo["play"] == "backoff" and bo["schema_version"] == 3 and bo == _mid3(True)
    # #645: uniform play keeps the L1/L2 counts of #635; the turn decision that stayed uniform now finds an L3 row
    assert _levels(uni) == {"0": dict(decisions=93, exact=90, L1=2, L2=0, L3=0, uniform=1),
                            "1": dict(decisions=14, exact=6, L1=2, L2=1, L3=0, uniform=5),
                            "2": dict(decisions=4, exact=1, L1=2, L2=0, L3=1, uniform=0),
                            "3": dict(decisions=0, exact=0, L1=0, L2=0, L3=0, uniform=0)}
    assert _levels(bo) == {"0": dict(decisions=93, exact=90, L1=2, L2=0, L3=0, uniform=1),
                           "1": dict(decisions=13, exact=6, L1=1, L2=1, L3=0, uniform=5),
                           "2": dict(decisions=3, exact=1, L1=0, L2=0, L3=1, uniform=1),
                           "3": dict(decisions=0, exact=0, L1=0, L2=0, L3=0, uniform=0)}
    for r in (uni, bo):
        for c in r["by_backoff"]["by_street"].values():
            assert c["exact"] + c["L1"] + c["L2"] + c["L3"] + c["uniform"] == c["decisions"]


def test_backoff_row_is_exact_then_coarse_then_none():
    a = "BTN|n3|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e5|o1v1k0"
    third = a.replace("s4:4", "s5:5")
    pol = {a: [1.0, 0.0]}
    tabs = H.coarse_tables(pol)
    assert H.backoff_row(pol, tabs, a, 2) == ([1.0, 0.0], 0)
    assert H.backoff_row(pol, tabs, third, 2) == ([1.0, 0.0], 1)
    assert H.backoff_row(pol, tabs, third, 3) == (None, 4)


def test_main_play_backoff_flag_and_legacy_refusal(mid3_shared, tmp_path, capsys):
    import shutil
    p = tmp_path / "mid-3.json"
    shutil.copy("web/app/policy/mid-3.json", p)
    assert H.main([str(p), "--hands", "1"]) == 0
    off = json.loads(capsys.readouterr().out)
    assert "play" not in off and "by_backoff" not in off
    assert H.main([str(p), "--hands", "1", "--play-backoff"]) == 0
    on = json.loads(capsys.readouterr().out)
    assert on["play"] == "backoff" and "by_backoff" in on
    leg = tmp_path / "t-3.json"
    leg.write_text(json.dumps({"q": 255, "players": N3, "k": K, "depth": DEPTH,
                               "policy": {"0|0|1|1|0|2|0|fcra|e0": [255, 0]}}), encoding="utf-8")
    try:
        H.main([str(leg), "--play-backoff"])
    except SystemExit as e:
        assert "legacy" in str(e)
    else:
        raise AssertionError("--play-backoff on a legacy table must stop")


# --- #638: breakdown of the decisions still uniform after the last level (L2, L3 since #645) ---

def test_release_fields_finds_the_one_field_that_would_hit_at_l2():
    a = "BTN|n3|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e5|o1v1k0"
    b = "BB|n3|1|1|0|2|1|0|tc0|s4:4|u10|hn|go|ka|e2"
    pol = {a: [1.0, 0.0], b: [0.5, 0.5], "call|1|1|2|fc|e3": [0.2, 0.8]}
    idx = H.masked_index(H.coarse_tables(pol))
    # a's L2 key with the equity step changed: releasing field 14 (equity) alone finds a's row
    assert H.release_fields(idx, a.replace("|e5|", "|e6|"), 2) == [14]
    # differs from b in position (0) and equity (14) — two fields, so no single release hits
    assert H.release_fields(idx, "BB|n3|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e9", 2) == []
    # differs from a only in the position and the dropped items: field 0
    assert H.release_fields(idx, "SB|n3|1|1|0|2|0|7|tc0|s9:9|u01|hb|gx|ka|e5", 2) == [0]
    assert H.release_fields(idx, a.replace("|e5|", "|e6|"), 3) == []   # no row of that length
    # a call key releases its pot-odds step (field 3; field 2 is already `*` at L2)
    assert H.release_fields(idx, "call|1|2|0|fc|e3", 2) == [3]


def _mid3_miss(top):
    from pathlib import Path
    pol, doc = H.load_policy(Path("web/app/policy/mid-3.json"))
    return H.measure(pol, doc["players"], doc["k"], doc["depth"], 20, 5, rules=H.rules_of(doc),
                     variant=H.variant_of(pol, doc), play_backoff=True, backoff=True, miss_report=top)


def test_miss_report_counts_the_l2_misses_and_leaves_the_play_unchanged(mid3_shared):
    bo, mr = _mid3(True), _mid3_miss(3)
    assert mr["schema_version"] == 4 and bo["schema_version"] == 3 and "miss_report" not in bo
    assert {k: v for k, v in mr.items() if k not in ("miss_report", "schema_version")} == \
        {k: v for k, v in bo.items() if k != "schema_version"}
    rep = mr["miss_report"]
    assert rep["top"] == 3
    for st, c in rep["by_street"].items():
        assert c["misses"] == bo["by_backoff"]["by_street"][st]["uniform"]
    flop = rep["by_street"]["1"]
    assert flop["misses"] == 5 and flop["distinct_keys"] == 5 and flop["any_field"] == 4
    assert flop["by_field"] == {"14": 4, "3": 2, "0": 1, "5": 1}
    # since #645 the report reads the last level (L3): position names are their groups
    assert flop["top_keys"] == [["blind|n3|1|2|0|2|0|*|tc0|s*|*|*|*|kb20b33b50b75b100b150a|e6", 1],
                                ["blind|n3|1|2|1|1|2|*|tc0|s*|*|*|*|fcr25ra|e1", 1],
                                ["late|n3|1|1|0|1|0|*|tc0|s*|*|*|*|kb20b33b50b75b100b150b200b300a|e7", 1]]
    assert rep["by_street"]["0"]["by_field"] == {"6": 1}
    assert rep["by_street"]["3"] == {"misses": 0, "distinct_keys": 0, "top_keys": [], "by_field": {}, "any_field": 0}
    assert mr == _mid3_miss(3)


def test_miss_report_off_is_byte_identical_and_needs_play_backoff(mid3_shared, tmp_path, capsys):
    import shutil
    import pytest
    p = tmp_path / "mid-3.json"
    shutil.copy("web/app/policy/mid-3.json", p)
    assert H.main([str(p), "--hands", "2", "--play-backoff"]) == 0
    plain = capsys.readouterr().out
    assert H.main([str(p), "--hands", "2", "--play-backoff", "--miss-report", "0"]) == 0
    assert capsys.readouterr().out == plain and '"miss_report"' not in plain
    assert H.main([str(p), "--hands", "2", "--play-backoff", "--miss-report", "4"]) == 0
    assert json.loads(capsys.readouterr().out)["miss_report"]["top"] == 4
    with pytest.raises(SystemExit, match="--play-backoff"):
        H.main([str(p), "--miss-report", "4"])
    with pytest.raises(ValueError):
        H.measure({}, N3, K, DEPTH, 1, 5, miss_report=2)


# --- #644: the run does not depend on PYTHONHASHSEED ---

def test_range_update_column_is_zero_on_dead_combos_and_finite(monkeypatch):
    """Dead combos (step -1) must weigh 0 in the Bayes column, as the page's seatProbs (zero-filled) does.
    An unfilled row read whatever memory held, NaN included, so the run varied across processes."""
    import numpy as np
    from pathlib import Path
    from stalker.e2.eq_view import N
    from stalker.e3 import tp_key as TK
    pol, doc = H.load_policy(Path("web/app/policy/mid-3.json"))
    seen, real_es, real_ur = [], TK.equity_steps, TK.update_range
    last = {}

    def es(*a, **k):
        last["steps"] = real_es(*a, **k)
        return last["steps"]

    def ur(ranges, seat, col):
        seen.append((last["steps"].copy(), np.array(col)))
        return real_ur(ranges, seat, col)

    monkeypatch.setattr(TK, "equity_steps", es)
    monkeypatch.setattr(TK, "update_range", ur)
    real_empty = np.empty

    def poisoned(shape, *a, **k):  # stale memory made visible: an unfilled (N, m) buffer reads NaN
        if not a and not k and isinstance(shape, tuple) and len(shape) == 2 and shape[0] == N:
            return np.full(shape, np.nan)
        return real_empty(shape, *a, **k)

    monkeypatch.setattr(np, "empty", poisoned)
    for play in (False, True):
        H.measure(pol, doc["players"], doc["k"], doc["depth"], 5, 5, rules=H.rules_of(doc),
                  variant=H.variant_of(pol, doc), play_backoff=play)
    assert seen and any((st < 0).any() for st, _ in seen)
    for st, col in seen:
        assert np.isfinite(col).all() and (col[st < 0] == 0).all()


@pytest.mark.slow
def test_play_backoff_output_is_byte_identical_across_hash_seeds():
    import os
    import subprocess
    import sys
    outs = []
    for h in ("0", "2"):
        env = {**os.environ, "PYTHONHASHSEED": h}
        outs.append(subprocess.run([sys.executable, "-m", "stalker.tools.web_hit_rate", "web/app/policy/mid-3.json",
                                    "--hands", "80", "--seed", "620", "--play-backoff", "--miss-report", "5"],
                                   env=env, check=True, capture_output=True).stdout)
    assert outs[0] == outs[1]


# --- #645: L3 = L2 with the position name -> its position group ---

def test_l3_replaces_the_position_name_with_its_group_at_every_player_count():
    from stalker.e3 import tp_key as TK
    tail = "|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e5|o1v1k0"
    for n in range(2, 7):
        for seat, name in enumerate(TK.C1_POSITIONS[n]):
            k = f"{name}|n{n}{tail}"
            l2 = H.coarse_key(k, 2)
            assert H.coarse_key(k, 3) == "|".join([TK.position_group(n, seat)] + l2.split("|")[1:])
    assert H.coarse_key("UTG|n6" + tail, 3).startswith("early|n6|")
    assert H.coarse_key("CO|n6" + tail, 3).startswith("late|n6|")
    assert H.coarse_key("BTN|n2" + tail, 3).startswith("blind|n2|")   # heads-up both seats post a blind
    assert H.coarse_key("CO|n4" + tail, 3).startswith("late|n4|")
    assert H.coarse_key("p|HJ|n5" + tail, 3).startswith("p|early|n5|")   # pro keys: the name is field 1
    for k in ("call|1|2|3|fc|e4", "b|n3|late|1|1|0|2|tc0|s4:4|u10|hn|ka|e5"):   # no position name: L3 = L2
        assert H.coarse_key(k, 3) == H.coarse_key(k, 2)


def test_a_key_found_only_at_l3_backs_off_to_the_group_mean():
    co = "CO|n6|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e5|o1v1k0"
    btn = co.replace("CO|", "BTN|")   # BTN shares CO's group (late) at 6 players, HJ (early) does not
    btn_u = btn.replace("|u10|", "|u01|")   # same L2 key as btn
    hj = co.replace("CO|", "HJ|")
    pol = {btn: [1.0, 0.0], btn_u: [0.0, 1.0], hj: [0.2, 0.8]}
    tabs = H.coarse_tables(pol)
    assert H.backoff_level(pol, tabs, co, 2) == 3
    assert H.backoff_row(pol, tabs, co, 2) == ([0.5, 0.5], 3)
    sb = co.replace("CO|", "SB|")   # blind group: no row
    assert H.backoff_row(pol, tabs, sb, 2) == (None, 4)


# --- #648: L4 = the L3 rows one equity step either side ---

_CO6 = "CO|n6|1|1|0|2|0|0|tc0|s4:4|u10|hn|go|ka|e{}|o1v1k0"


def _l4(pol, key, m=2, top=K - 1):
    tabs = H.coarse_tables(pol)
    return H.backoff_row(pol, tabs, key, m, top)


def test_l4_averages_both_neighbors_or_takes_the_one_found():
    pol = {_CO6.format(4): [1.0, 0.0], _CO6.format(6): [0.0, 1.0]}
    assert _l4(pol, _CO6.format(5)) == ([0.5, 0.5], 4)   # (a) both sides
    assert _l4(pol, _CO6.format(7)) == ([0.0, 1.0], 4)   # (b) only e6
    assert _l4(pol, _CO6.format(8)) == (None, 5)         # (d) no neighbor -> uniform, one level past L4
    assert H.backoff_row(pol, H.coarse_tables(pol), _CO6.format(5), 2) == (None, 4)   # off: the old lookup
    assert _l4(pol, _CO6.format(5), m=3) == (None, 5)    # rows of another length are never used


def test_l4_skips_steps_outside_0_to_top():
    # (c) the lowest step has only an upper neighbor; a row at top+1 exists only in a hand-made table and is never read
    pol = {_CO6.format(1): [1.0, 0.0], _CO6.format(K - 2): [0.0, 1.0], _CO6.format(K): [1.0, 0.0]}
    assert _l4(pol, _CO6.format(0)) == ([1.0, 0.0], 4)
    assert _l4(pol, _CO6.format(K - 1)) == ([0.0, 1.0], 4)


def test_l4_on_call_and_basic_keys():
    # (e) the equity field is found wherever it sits; the rest of the L3 key stays
    call = {"call|1|*|3|fc|e3": [0.2, 0.8]}
    assert _l4(call, "call|1|2|3|fc|e4") == ([0.2, 0.8], 4)
    assert _l4(call, "call|1|2|2|fc|e4") == (None, 5)
    basic = "b|n3|late|1|1|0|2|tc0|s4:4|u10|hn|ka|e{}"
    pol = {basic.format(2): [0.4, 0.6], basic.format(4): [0.6, 0.4]}
    assert _l4(pol, basic.format(3), top=4) == ([0.5, 0.5], 4)
    assert _l4(pol, basic.format(3).replace("|late|", "|blind|"), top=4) == (None, 5)


def test_l4_counts_a_level_and_off_is_byte_identical(mid3_shared, tmp_path, capsys):
    import shutil
    p = tmp_path / "mid-3.json"
    shutil.copy("web/app/policy/mid-3.json", p)
    args = [str(p), "--hands", "3", "--seed", "620", "--play-backoff", "--miss-report", "3"]
    assert H.main(args) == 0
    off = capsys.readouterr().out
    assert '"l4_neighbor"' not in off and '"L4"' not in off
    assert H.main(args) == 0
    assert capsys.readouterr().out == off
    assert H.main(args + ["--l4-neighbor"]) == 0
    on = json.loads(capsys.readouterr().out)
    assert on["l4_neighbor"] is True and on["schema_version"] == 5
    assert on["by_backoff"]["levels"] == ["exact", "L1", "L2", "L3", "L4", "uniform"]
    o = json.loads(off)
    for st, c in on["by_backoff"]["by_street"].items():
        assert sum(c[k] for k in on["by_backoff"]["levels"]) == c["decisions"]
        assert set(c["rate"]) == set(on["by_backoff"]["levels"])
    assert H.main([str(p), "--hands", "3", "--l4-neighbor"]) == 0   # implies --backoff, play stays uniform
    b = json.loads(capsys.readouterr().out)
    assert "by_backoff" in b and "play" not in b
    assert o["schema_version"] == 4


@pytest.mark.slow
def test_l4_output_is_byte_identical_across_hash_seeds():
    import os
    import subprocess
    import sys
    outs = []
    for h in ("0", "2"):
        env = {**os.environ, "PYTHONHASHSEED": h}
        outs.append(subprocess.run([sys.executable, "-m", "stalker.tools.web_hit_rate", "web/app/policy/mid-3.json",
                                    "--hands", "80", "--seed", "620", "--play-backoff", "--l4-neighbor",
                                    "--miss-report", "5"], env=env, check=True, capture_output=True).stdout)
    assert outs[0] == outs[1] and b'"L4"' in outs[0]


# --- #666: play-weighted backoff fidelity ---

def _fid_table():
    from stalker.e3 import game as G
    import numpy as np
    spy = Spy()
    H.measure(spy, N3, K, DEPTH, 1, 5)
    a = spy.asked[0]
    m = len(G.legal(G.deal(np.random.default_rng([5, 611, N3]), N3)))
    sib = a.replace("|s6:6|", "|s7:7|", 1)   # same L1 key (stack depths are dropped there)
    assert sib != a and H.coarse_key(sib, 1) == H.coarse_key(a, 1)
    ra, rb = [0.0] * m, [0.0] * m
    ra[0], rb[1] = 1.0, 1.0
    return a, m, {a: ra, sib: rb}, ra, rb


def test_fidelity_weighs_by_decisions_and_exact_numbers():
    a, m, pol, ra, rb = _fid_table()
    r = H.measure(pol, N3, K, DEPTH, 4, 5, play_backoff=True, fidelity=True)
    assert r["schema_version"] == 6
    f = r["fidelity"]
    assert set(f) == {"0", "1", "2", "3"}
    n_a = r["by_street"]["0"]["hits"]   # a and its sibling are the only rows, both preflop
    got = f["0"]["L1"]
    assert n_a == 1 and got["n"] == 1 and "uniform" not in f["0"]   # the sibling is never played, so only `a` hits, via L1
    # the approximation of one pure row is the other pure row: TV 1, argmax wrong; uniform has TV 1 - 1/m
    assert got["tv_mean"] == 1.0 and got["argmax_agree"] == 0.0
    assert got["uniform_tv_mean"] == round(1 - 1.0 / m, 6) and got["uniform_argmax_agree"] == round(1.0 / m, 6)
    assert f["1"] == {} and f["2"] == {} and f["3"] == {}


def test_fidelity_is_weighted_by_decisions_not_keys(monkeypatch):
    from collections import Counter
    from stalker.e3 import game as G
    from stalker.tools import backoff_fidelity as BF
    import numpy as np
    spy = Spy()
    H.measure(spy, N3, K, DEPTH, 12, 5)
    k1, k2 = [k for k, _ in Counter(spy.asked).most_common() if "|s6:6|" in k][:2]
    m = len(G.legal(G.deal(np.random.default_rng([5, 611, N3]), N3)))
    pure = lambda i: [1.0 if j == i else 0.0 for j in range(m)]
    half = [0.5, 0.5] + [0.0] * (m - 2)
    sib = lambda k: k.replace("|s6:6|", "|s7:7|", 1)   # same L1 key, never played, so it is the only other row of the group
    pol = {k1: pure(0), sib(k1): half, k2: pure(0), sib(k2): pure(1)}
    seen: Counter = Counter()
    orig = BF.loo_row
    monkeypatch.setattr(BF, "loo_row", lambda sums, key, row, l4=None: (seen.update([key]), orig(sums, key, row, l4))[1])
    r = H.measure(pol, N3, K, DEPTH, 12, 5, play_backoff=True, fidelity=True)
    n1, n2 = seen[k1], seen[k2]
    assert max(n1, n2) >= 2 and n1 != n2 and set(seen) == {k1, k2}   # one key repeats, the two keys occur a different number of times
    got = r["fidelity"]["0"]["L1"]
    assert got["n"] == n1 + n2 == r["by_street"]["0"]["hits"]
    tv = {k1: 0.5, k2: 1.0}     # k1: pure(0) vs half; k2: pure(0) vs pure(1)
    agree = {k1: 1.0, k2: 0.0}  # half's argmax is 0 (first max)
    n = {k1: n1, k2: n2}
    w_tv = sum(n[k] * tv[k] for n in [n] for k in n) / (n1 + n2)
    w_ag = sum(n[k] * agree[k] for k in n) / (n1 + n2)
    assert got["tv_mean"] == round(w_tv, 6) and got["argmax_agree"] == round(w_ag, 6)
    assert w_tv != (tv[k1] + tv[k2]) / 2 and w_ag != 0.5   # a per-key average would give other numbers


def test_fidelity_off_is_byte_identical_and_needs_play_backoff(mid3_shared, tmp_path, capsys):
    import shutil
    p = tmp_path / "mid-3.json"
    shutil.copy("web/app/policy/mid-3.json", p)
    args = [str(p), "--hands", "3", "--seed", "620", "--play-backoff", "--l4-neighbor"]
    assert H.main(args) == 0
    off = capsys.readouterr().out
    assert '"fidelity"' not in off
    assert H.main(args + ["--fidelity"]) == 0
    on = capsys.readouterr().out
    d = json.loads(on)
    assert d["schema_version"] == 6 and d["fidelity"]
    assert H.main(args + ["--fidelity"]) == 0 and capsys.readouterr().out == on
    rest = {k: v for k, v in d.items() if k not in ("fidelity", "schema_version")}
    base = {k: v for k, v in json.loads(off).items() if k != "schema_version"}
    assert rest == base   # the play is unchanged
    with pytest.raises(SystemExit, match="--play-backoff"):
        H.main([str(p), "--fidelity"])
    with pytest.raises(ValueError):
        H.measure({}, N3, K, DEPTH, 1, 5, fidelity=True)


# --- #743: backoff tables from a table other than the exact one ---

def test_coarse_policy_none_or_same_table_is_byte_identical():
    key = _first_key()
    pol = {key: [0.5, 0.5]}
    kw = dict(play_backoff=True, l4_neighbor=True)
    base = H.measure(pol, N3, K, DEPTH, 3, 5, **kw)
    assert json.dumps(H.measure(pol, N3, K, DEPTH, 3, 5, coarse_policy=None, **kw)) == json.dumps(base)
    assert json.dumps(H.measure(pol, N3, K, DEPTH, 3, 5, coarse_policy=pol, **kw)) == json.dumps(base)


def test_a_key_only_in_coarse_policy_is_found_at_l1_not_exact():
    key = _first_key()
    for m in range(2, 7):   # the first decision's menu size is the engine's; try each row length
        r = H.measure({}, N3, K, DEPTH, 1, 5, backoff=True, coarse_policy={key: [1.0 / m] * m})
        bb = r["by_backoff"]
        if sum(c["L1"] for c in bb["by_street"].values()):
            break
    assert sum(c["L1"] for c in bb["by_street"].values()) >= 1
    assert sum(c["exact"] for c in bb["by_street"].values()) == 0
    assert bb["keys"]["exact"] == 0 and bb["keys"]["L1"] >= 1


def test_l1_extra_rows_are_found_at_l1_and_empty_or_none_changes_nothing():
    # #790: rows shipped beside the file feed level 1 only; exact lookups stay on the policy
    key = _first_key()
    pol = {key: [0.5, 0.5]}
    kw = dict(play_backoff=True, l4_neighbor=True)
    base = json.dumps(H.measure(pol, N3, K, DEPTH, 3, 5, **kw))
    assert json.dumps(H.measure(pol, N3, K, DEPTH, 3, 5, l1_extra=None, **kw)) == base
    assert json.dumps(H.measure(pol, N3, K, DEPTH, 3, 5, l1_extra={}, **kw)) == base
    ck = H.coarse_key(key, 1)
    for m in range(2, 7):
        r = H.measure({}, N3, K, DEPTH, 1, 5, backoff=True, l1_extra={ck: {m: [1.0 / m] * m}})
        bb = r["by_backoff"]
        if sum(c["L1"] for c in bb["by_street"].values()):
            break
    assert sum(c["L1"] for c in bb["by_street"].values()) >= 1
    assert sum(c["exact"] for c in bb["by_street"].values()) == 0
