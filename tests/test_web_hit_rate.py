"""#611: web policy table hit-rate tool."""
import json

from stalker.tools import web_hit_rate as H

K, DEPTH, N3 = 11, "full", 3


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
    assert H.backoff_level(pol, tabs, third, 4) == 3   # no row of that length at any level: uniform
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
    assert bb["levels"] == ["exact", "L1", "L2", "uniform"]
    for st, c in bb["by_street"].items():
        assert c["decisions"] == off["by_street"][st]["decisions"]
        assert c["exact"] == off["by_street"][st]["hits"]
        assert c["exact"] + c["L1"] + c["L2"] + c["uniform"] == c["decisions"]


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
