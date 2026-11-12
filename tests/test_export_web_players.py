"""#588: cloud.yml mode=export -> per-seat-count web policy files and their ops summary."""
import hashlib
import json
from pathlib import Path

import pytest

from stalker.e3.mccfr import E3MCCFR, key_players
from stalker.tools import export_web_players as W
from stalker.tools import pod_train as P

FIVE = (2, 3, 4, 5, 6)


def _pod_result(tmp_path, m, name="pod"):
    """What pod_train.run leaves for a model (evaluation stubbed): the shape `cloud-result-<run>` holds."""
    model = {"k": m.k, "n": m.n, "depth": m.depth, "iterations": m.iterations, "nodes": m.nodes, "menu": m.menu,
             "raise_cap": m.raise_cap, "avg_rule": m.avg_rule, "rng": m.rng.bit_generator.state, **m._grid()}
    if m.key_variant:
        from stalker.e3 import tp_key as K

        model.update(key_variant=m.key_variant, stacks=m.stacks, key_version=K.KEY_VERSIONS[m.key_variant])
    if m.player_mix:
        model.update(player_mix=list(m.player_mix), **m._count_state())
    res = {"job": "e3-tp-beginner-c1-mixn-pod", "tier": "beginner", "iters": m.iterations, "model": model,
           "by_players": {str(n): {"lbr": {"lbr_bb": n / 10, "stderr_bb": 0.01},
                                   "field": {"worst": {"name": "nit1", "bb100": -float(n)}}} for n in m.player_mix or ()},
           **P._checkpoint(m, P.RESULT_BUDGET, P.RESUME_BUDGET)}
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(res), encoding="utf-8")
    return path


@pytest.mark.slow
def test_export_writes_five_unmixed_files_index_and_summary(tmp_path):
    m = E3MCCFR(3, 5, 6, "basic", key_variant="c1", player_mix=FIVE)
    m.iterate(8)   # seed 3: every one of 2..6 owns keys
    res = _pod_result(tmp_path, m)
    base = json.loads((Path(__file__).parents[1] / "web" / "app" / "policy" / "index.json").read_text(encoding="utf-8"))
    base_path = tmp_path / "base-index.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    out, sm = tmp_path / "out", tmp_path / "ops" / "cloud" / "exports" / "41.json"
    assert W.main(["export", "--pod-result", str(res), "--run", "41", "--tier", "beginner",
                   "--index-base", str(base_path), "--out-dir", str(out), "--summary-out", str(sm)]) == 0
    assert sorted(p.name for p in out.iterdir()) == [f"beginner-{n}.json" for n in FIVE] + ["index.json"]
    s = json.loads(sm.read_text(encoding="utf-8"))
    assert (s["export_run"], s["tier"], s["player_mix"], s["artifact"]) == ("41", "beginner", list(FIVE), "web-policy-41")
    cur = m.current_policy()
    for f in s["files"]:
        body = (out / f["file"]).read_bytes()
        doc = json.loads(body)
        n = f["players"]
        # no seat count leaks into another's file, each file holds all of its own keys and the shared call| keys (#610)
        assert {key_players(k) for k in doc["policy"]} == {n, None}
        assert set(doc["policy"]) == {k for k in cur if key_players(k) in (n, None)}
        assert (f["keys"], f["bytes"], f["sha256"]) == (doc["keys"], len(body), hashlib.sha256(body).hexdigest())
        assert (f["lbr_bb"], doc["lbr_bb"], f["field_worst"]["name"]) == (n / 10, n / 10, "nit1")
        assert f["within_page_budget"] is True and f["keys_by_min_visits"]["1"] <= f["keys"]
    ib = (out / "index.json").read_bytes()
    assert s["index"] == {"file": "index.json", "bytes": len(ib), "sha256": hashlib.sha256(ib).hexdigest()}
    tiers = json.loads(ib)["tiers"]
    assert tiers["beginner"]["file"] == "beginner-6.json" and tiers["beginner"]["run_id"] == "41"
    assert {k: v["file"] for k, v in tiers["beginner"]["by_players"].items()} == {str(n): f"beginner-{n}.json" for n in FIVE[:-1]}
    assert tiers["mid"] == base["tiers"]["mid"] and tiers["pro"] == base["tiers"]["pro"]   # other tiers untouched
    with pytest.raises(SystemExit, match="pass tier=beginner"):
        W.main(["export", "--pod-result", str(res), "--run", "41", "--tier", "mid",
                "--out-dir", str(tmp_path / "o2"), "--summary-out", str(tmp_path / "s2.json")])


def test_export_summary_marks_oversize_files_and_counts_keys_per_visit_floor(tmp_path):
    m = E3MCCFR(1, 5, 6, "basic", key_variant="c1", player_mix=(2, 4, 6))
    m.iterate(3)
    st = m.state()
    s = W.export_all_players(st, {"job": "j"}, "7", tmp_path, players=(2, 4, 6), max_bytes=1)
    visits = dict(m.visits)
    for f in s["files"]:
        own = [k for k in m.current_policy() if key_players(k) in (f["players"], None)]
        assert any(k.startswith("call|") for k in own)   # #610: the shared call| keys count toward every file
        assert f["within_page_budget"] is False and (tmp_path / f["file"]).exists()
        assert f["keys_by_min_visits"] == {str(v): sum(visits.get(k, 0) >= v for k in own) for v in W.VISIT_STEPS}
        assert f["lbr_bb"] is None   # no by_players row: empty, still exported
    s3 = W.export_all_players(st, {}, "7", tmp_path / "mv", players=(4,), min_visits=3)
    f4 = s3["files"][0]
    assert f4["keys"] + f4["keys_dropped"] == sum(key_players(k) in (4, None) for k in m.current_policy()) and f4["keys_dropped"] > 0
    assert s3["min_visits"] == 3 and all(visits[k] >= 3 for k in json.loads((tmp_path / "mv" / "beginner-4.json").read_text(encoding="utf-8"))["policy"])


def test_keys_by_min_visits_has_floors_3_and_4_for_the_six_seat_choice():
    # #718: #714 named 6-seat floors 3-4 as candidates; the summary must size them without another export
    visits = {"a": 1, "b": 2, "c": 3, "d": 3, "e": 4, "f": 5}
    got = W._keys_by_min_visits([*visits, "unseen"], visits)
    assert list(got) == ["1", "2", "3", "4", "5", "10", "20", "50", "100"]
    assert (got["1"], got["2"], got["3"], got["4"], got["5"], got["10"]) == (6, 5, 4, 2, 1, 0)
    counts = list(got.values())
    assert all(a >= b for a, b in zip(counts, counts[1:]))


def test_export_refuses_a_table_without_player_mix(tmp_path):
    m = E3MCCFR(1, 5, 6, "basic")
    m.iterate(2)
    res = _pod_result(tmp_path, m)
    with pytest.raises(SystemExit, match="no player_mix .*export_web_policy --pod-result") as e:
        W.main(["export", "--pod-result", str(res), "--run", "8", "--out-dir", str(tmp_path / "o"),
                "--summary-out", str(tmp_path / "s.json")])
    assert e.value.code not in (0, None)
    assert not (tmp_path / "s.json").exists()


def test_missing_or_expired_artifact_fails_with_the_fix(tmp_path):
    msg = r"^artifact cloud-result-9 not found/expired: 다시 학습하거나 다른 run을 지정"
    live = {"name": "cloud-result-9", "expired": False, "id": 1}
    assert W.check_artifact({"artifacts": [live]}, "9") == live
    for listing in ({"artifacts": []}, {"artifacts": [{**live, "expired": True}]},
                    {"artifacts": [{**live, "name": "cloud-result-10"}]}, {}):
        with pytest.raises(SystemExit, match=msg):
            W.check_artifact(listing, "9")
    bad = tmp_path / "listing.json"
    bad.write_text("not json (gh api 404)", encoding="utf-8")
    with pytest.raises(SystemExit, match=msg):
        W.main(["check-artifact", str(bad), "--run", "9"])
    with pytest.raises(SystemExit, match=msg):
        W.main(["export", "--pod-result", str(tmp_path / "none.json"), "--run", "9",
                "--out-dir", str(tmp_path / "o"), "--summary-out", str(tmp_path / "s.json")])


def test_min_visits_by_players_parses_and_rejects_with_the_fix():
    assert W.parse_min_visits_by_players("2:10, 3:5,6:2", (2, 3, 4, 5, 6)) == {2: 10, 3: 5, 6: 2}
    assert W.parse_min_visits_by_players("", FIVE) == {}
    for bad, msg in (("2-10", "is not <players>:<count>"), ("2:x", "is not <players>:<count>"),
                     ("7:1", "not in this run's player_mix"), ("2:1,2:3", "appears twice")):
        with pytest.raises(SystemExit, match=msg):
            W.parse_min_visits_by_players(bad, FIVE)


def test_per_player_min_visits_is_applied_and_recorded_per_file(tmp_path):
    m = E3MCCFR(1, 5, 6, "basic", key_variant="c1", player_mix=(2, 4, 6))
    m.iterate(40)
    st = m.state()
    s = W.export_all_players(st, {"job": "j"}, "7", tmp_path, players=(2, 4, 6), min_visits=1,
                             min_visits_by_players={4: 3})
    assert {f["players"]: f["min_visits"] for f in s["files"]} == {2: 1, 4: 3, 6: 1}
    assert s["min_visits_by_players"] == {"4": 3}
    visits = dict(m.visits)
    kept = json.loads((tmp_path / "beginner-4.json").read_text(encoding="utf-8"))["policy"]
    assert kept and all(visits[k] >= 3 for k in kept)
    # CLI: a bad spec fails before anything is written
    res = _pod_result(tmp_path, m)
    with pytest.raises(SystemExit, match="appears twice"):
        W.main(["export", "--pod-result", str(res), "--run", "7", "--min-visits-by-players", "2:1,2:2",
                "--out-dir", str(tmp_path / "o"), "--summary-out", str(tmp_path / "s.json")])
    assert not (tmp_path / "s.json").exists()


def test_policies_for_ops_keeps_only_files_within_the_page_budget(tmp_path):
    m = E3MCCFR(1, 5, 6, "basic", key_variant="c1", player_mix=(2, 4, 6))
    m.iterate(4)
    st = m.state()
    s = W.export_all_players(st, {"job": "j"}, "7", tmp_path, players=(2, 4, 6))
    sizes = sorted(f["bytes"] for f in s["files"])
    cap = sizes[0]   # only the smallest file fits
    s = W.export_all_players(st, {"job": "j"}, "7", tmp_path, players=(2, 4, 6), max_bytes=cap)
    fits = {f["file"] for f in s["files"] if f["within_page_budget"]}
    assert fits and len(fits) < 3
    out = W.policies_for_ops(s, tmp_path)
    assert set(out) == fits | {"index.json"}
    idx = json.loads(out["index.json"])
    listed = {e["file"] for t in idx["tiers"].values() for e in [t, *t.get("by_players", {}).values()] if "file" in e}
    assert listed == fits   # the index never names a file that was not uploaded
    # nothing fits: nothing to commit, and the summary still tells why
    s0 = W.export_all_players(st, {"job": "j"}, "7", tmp_path, players=(2, 4, 6), max_bytes=1)
    assert W.policies_for_ops(s0, tmp_path) == {}
    assert all(f["within_page_budget"] is False for f in s0["files"])


def test_cli_policies_out_index_lists_only_uploaded_files_of_this_run(tmp_path, monkeypatch):
    """The real path: one non-empty --index-base feeds both the full index and the ops copy (#596 review)."""
    m = E3MCCFR(1, 5, 6, "basic", key_variant="c1", player_mix=(2, 4, 6))
    m.iterate(4)
    res = _pod_result(tmp_path, m)
    base = json.loads((Path(__file__).parents[1] / "web" / "app" / "policy" / "index.json").read_text(encoding="utf-8"))
    base_path = tmp_path / "base-index.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    common = ["export", "--pod-result", str(res), "--run", "7", "--players", "2,4,6", "--index-base", str(base_path)]
    full = tmp_path / "full"
    W.main([*common, "--out-dir", str(full), "--summary-out", str(tmp_path / "all.json")])
    sizes = sorted((full / f"beginner-{n}.json").stat().st_size for n in (2, 4, 6))
    real = W.export_all_players
    monkeypatch.setattr(W, "export_all_players", lambda *a, **k: real(*a, **k, max_bytes=sizes[0]))  # only the smallest fits
    out, pol = tmp_path / "out", tmp_path / "pol"
    W.main([*common, "--out-dir", str(out), "--summary-out", str(tmp_path / "s.json"), "--policies-out", str(pol)])
    s = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    fits = {f["file"] for f in s["files"] if f["within_page_budget"]}
    assert fits and len(fits) < 3
    assert {p.name for p in pol.iterdir()} == fits | {"index.json"}
    idx = json.loads((pol / "index.json").read_text(encoding="utf-8"))
    ours = {e["file"] for t in idx["tiers"].values() for e in [t, *t.get("by_players", {}).values()]
            if e.get("run_id") == "7"}
    assert ours == fits


@pytest.mark.slow
def test_hit_rate_is_recorded_per_file_monotone_deterministic_and_can_be_turned_off(tmp_path):
    m = E3MCCFR(1, 5, 6, "basic", key_variant="c1", player_mix=(2, 3))
    m.iterate(30)
    st = m.state()
    off = W.export_all_players(st, {"job": "j"}, "7", tmp_path / "off", players=(2, 3))
    assert all("hit_rate" not in f for f in off["files"])
    a = W.export_all_players(st, {"job": "j"}, "7", tmp_path / "a", players=(2, 3), hit_rate_hands=3)
    b = W.export_all_players(st, {"job": "j"}, "7", tmp_path / "b", players=(2, 3), hit_rate_hands=3)
    for x in (a, b):   # wall-clock seconds are the one field that may differ between runs
        assert all(f.pop("hit_rate_seconds") >= 0 for f in x["files"])
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["schema_version"] == 3
    for f in a["files"]:
        hr = f["hit_rate"]
        assert list(hr["by_min_visits"]) == ["0", "1", "2", "5", "10"] and hr["players"] == f["players"]
        hits = [sum(c["hits"] for c in hr["by_min_visits"][v]["by_street"].values()) for v in hr["by_min_visits"]]
        assert hits == sorted(hits, reverse=True)   # a higher floor never finds more keys


def test_hit_rate_is_measured_with_the_files_own_menu_and_cap(tmp_path, monkeypatch):
    # a real-menu table measured with the engine default (v1, cap 3) reads ~0% off-`call|` (#618, #617 review)
    m = E3MCCFR(1, 5, 6, "basic", menu="real", raise_cap=None, key_variant="c1", player_mix=(2, 3))
    m.iterate(5)
    seen = []
    real = W.H.measure
    monkeypatch.setattr(W.H, "measure", lambda *a, **k: seen.append(k.get("rules")) or real(*a, **k))
    W.export_all_players(m.state(), {"job": "j"}, "7", tmp_path, players=(2, 3), hit_rate_hands=1)
    assert seen == [{"menu": "real", "raise_cap": None}] * 2


def test_v1_summary_without_hit_rate_still_feeds_policies_for_ops(tmp_path):
    m = E3MCCFR(1, 5, 6, "basic", key_variant="c1", player_mix=(2, 3))
    m.iterate(5)
    s = W.export_all_players(m.state(), {"job": "j"}, "7", tmp_path, players=(2, 3))
    s["schema_version"] = 1
    assert "index.json" in W.policies_for_ops(s, tmp_path, None)


def test_cli_default_hit_rate_hands_is_on(tmp_path):
    assert W.HIT_RATE_HANDS > 0


@pytest.mark.slow
def test_coarse_from_full_is_recorded_only_with_a_threshold_and_is_deterministic(tmp_path):
    m = E3MCCFR(1, 5, 6, "basic", key_variant="c1", player_mix=(2, 3))
    m.iterate(30)
    st = m.state()
    a = W.export_all_players(st, {"job": "j"}, "7", tmp_path / "a", players=(2, 3), hit_rate_hands=2, min_visits=2)
    b = W.export_all_players(st, {"job": "j"}, "7", tmp_path / "b", players=(2, 3), hit_rate_hands=2, min_visits=2)
    z = W.export_all_players(st, {"job": "j"}, "7", tmp_path / "z", players=(2, 3), hit_rate_hands=2)
    assert all("coarse_from_full" not in f["hit_rate"]["by_min_visits"] for f in z["files"])
    for x in (a, b):
        for f in x["files"]:
            f.pop("hit_rate_seconds")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    for f in a["files"]:
        c = f["hit_rate"]["by_min_visits"]["coarse_from_full"]
        assert c["min_visits"] == 2 and c["by_backoff"]["levels"][-1] == "uniform"


def _key(pos, stack, step, actions="fc"):
    return f"{pos}|n2|0|1|1|0|2|0|tc0|{stack}|u10|hb|{actions}|e{step}"


def test_l1_rows_bytes_matches_hand_counted_bodies_per_encoding():
    # #775: L1 drops the stack field, so the two BB e0 keys share an L1 row; mean (.75, .25) quantizes to [191, 64]
    before = {_key("BB", "s4:4", 0): [0.5, 0.5], _key("BB", "s6:6", 0): [1.0, 0.0],
              _key("BB", "s4:4", 1): [0.0, 1.0], _key("SB", "s4:4", 3): [0.2, 0.8],
              _key("SB", "s1:1", 3): [0.0, 1.0, 0.0]}   # same L1 key as the SB row above, another row length
    visits = {_key("BB", "s4:4", 0): 10, _key("BB", "s6:6", 0): 1, _key("BB", "s4:4", 1): 1, _key("SB", "s4:4", 3): 5}
    kept = {k: r for k, r in before.items() if visits.get(k, 0) >= 5}
    bb0, bb1, sb3 = (_key(p, "s*", e) for p, e in (("BB", 0), ("BB", 1), ("SB", 3)))
    all_body = f'{{"{bb0}":[191,64],"{bb1}":[0,255],"{sb3}":[[51,204],[0,255,0]]}}'
    missing_body = f'{{"{bb1}":[0,255],"{sb3}":[0,255,0]}}'
    bbg, sbg = _key("BB", "s*", "*"), _key("SB", "s*", "*")
    grouped_body = f'{{"{bbg}":{{"1":[0,255]}},"{sbg}":{{"3":[0,255,0]}}}}'
    r = W.l1_rows_bytes(before, kept, visits, 100, 10_000)
    assert (r["l1_keys_before"], r["l1_keys_file"]) == (3, 2)
    e = r["encodings"]
    assert list(e) == list(W.L1_ENCODINGS)
    assert [e[x]["bytes"] for x in ("all", "missing_only", "grouped_eq")] == [len(all_body), len(missing_body), len(grouped_body)]
    assert [e[x]["rows"] for x in ("all", "missing_only", "grouped_eq")] == [4, 2, 2]
    assert all(e[x]["l1_keys"] == 3 and e[x]["l1_keys_ratio"] == 1.0 for x in ("all", "missing_only", "grouped_eq"))
    assert e["all"]["total_bytes"] == 100 + len(all_body) and e["all"]["within_page_budget"] is True
    assert e["grouped_top_fit"] == e["grouped_eq"]   # room for every group
    assert e["all"]["gzip_bytes"] == len(W.gzip.compress(all_body.encode(), mtime=0))
    # BB's group carries visits 1 (its missing e1 key), SB's 0: with room for one group only BB's is kept
    one = len(f'{{"{bbg}":{{"1":[0,255]}}}}')
    t = W.l1_rows_bytes(before, kept, visits, 100, 100 + one + 1)["encodings"]["grouped_top_fit"]
    assert (t["bytes"], t["rows"], t["l1_keys"], t["l1_keys_ratio"]) == (one, 1, 3, 1.0)
    # SB e3 is still an L1 key the page has (its 2-row from kept), so the ratio only counts keys, not lengths
    none = W.l1_rows_bytes(before, kept, visits, 100, 100 + one)["encodings"]["grouped_top_fit"]
    assert (none["bytes"], none["rows"], none["l1_keys"], none["l1_keys_ratio"]) == (2, 0, 2, 0.6667)


def test_l1_rows_bytes_is_recorded_only_with_a_threshold_and_v2_summaries_still_read(tmp_path):
    m = E3MCCFR(1, 5, 6, "basic", key_variant="c1", player_mix=(2, 3))
    m.iterate(5)
    st = m.state()
    z = W.export_all_players(st, {"job": "j"}, "7", tmp_path / "z", players=(2, 3))
    assert all("l1_rows_bytes" not in f for f in z["files"])
    a = W.export_all_players(st, {"job": "j"}, "7", tmp_path / "a", players=(2, 3), min_visits=2)
    for f in a["files"]:
        r = f["l1_rows_bytes"]
        assert r["file_bytes"] == f["bytes"] and r["l1_keys_file"] <= r["l1_keys_before"]
        e = r["encodings"]
        assert e["missing_only"]["bytes"] <= e["all"]["bytes"] and e["grouped_top_fit"]["rows"] <= e["grouped_eq"]["rows"]
    v2 = json.loads(json.dumps(a))
    v2["schema_version"] = 2
    for f in v2["files"]:
        f.pop("l1_rows_bytes")
    assert W.policies_for_ops(v2, tmp_path / "a", None) == W.policies_for_ops(a, tmp_path / "a", None)


def test_top_fit_selection_is_the_one_l1_rows_bytes_reports():
    # #790: the hit-rate cell and the byte report must pick the same rows (one function)
    before = {_key("BB", "s4:4", 0): [0.5, 0.5], _key("BB", "s4:4", 1): [0.0, 1.0], _key("SB", "s4:4", 3): [0.2, 0.8]}
    visits = {_key("BB", "s4:4", 0): 10, _key("BB", "s4:4", 1): 1, _key("SB", "s4:4", 3): 5}
    kept = {k: r for k, r in before.items() if visits[k] >= 5}
    for room in (10_000, 130, 100):
        fit_rows = W._top_fit(before, kept, visits, 100, room)[3]
        r = W.l1_rows_bytes(before, kept, visits, 100, room)["encodings"]["grouped_top_fit"]
        assert r["rows"] == sum(len(d) for d in fit_rows.values())
        assert r["l1_keys"] == len(set(fit_rows) | set(W._l1_rows(kept)))
    assert W._top_fit(before, kept, visits, 100, 100)[3] == {}   # no room: no rows


@pytest.mark.slow
def test_coarse_top_fit_cell_with_no_room_equals_the_file_alone_and_is_deterministic(tmp_path):
    m = E3MCCFR(1, 5, 6, "basic", key_variant="c1", player_mix=(2, 3))
    m.iterate(30)
    st = m.state()
    kw = dict(players=(2,), hit_rate_hands=2, min_visits=2)
    a = W.export_all_players(st, {"job": "j"}, "7", tmp_path / "a", **kw)
    b = W.export_all_players(st, {"job": "j"}, "7", tmp_path / "b", **kw)
    z = W.export_all_players(st, {"job": "j"}, "7", tmp_path / "z", max_bytes=1, **kw)   # no room for any row
    for x in (a, b, z):
        for f in x["files"]:
            f.pop("hit_rate_seconds")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    c = a["files"][0]["hit_rate"]["by_min_visits"]["coarse_top_fit"]
    assert c["min_visits"] == 2 and c["by_backoff"]["levels"][-1] == "uniform"
    zc = z["files"][0]["hit_rate"]["by_min_visits"]["coarse_top_fit"]
    assert zc["l1_rows"] == 0
    # no room = the file's own table alone: the same hands played without `l1_extra` give the same by_backoff
    doc = json.loads((tmp_path / "z" / z["files"][0]["file"]).read_bytes())
    before = W.X.keep_players(W.X.load_model(st).current_policy(), 2)
    visits = dict(W.X.load_model(st).visits)
    kept = {k: r for k, r in before.items() if visits.get(k, 0) >= 2}
    alone = W.H.measure(kept, 2, doc["k"], doc["depth"], 2, 611 + 2, rules=W.H.rules_of(doc),
                      play_backoff=True, l4_neighbor=True)
    assert json.dumps(zc["by_backoff"], sort_keys=True) == json.dumps(alone["by_backoff"], sort_keys=True)


def test_top_fit_with_room_for_everything_restores_every_l1_row_the_threshold_erased():
    # #790: with a generous cap the file's L1 rows plus the shipped rows cover the pre-threshold L1 (key, length) set,
    # which is what `coarse_from_full` builds from. Row values may differ (quantize); L2+ differ by definition.
    before = {_key("BB", "s4:4", 0): [0.5, 0.5], _key("BB", "s6:6", 0): [1.0, 0.0], _key("BB", "s4:4", 1): [0.0, 1.0],
              _key("SB", "s4:4", 3): [0.2, 0.8], _key("SB", "s1:1", 3): [0.0, 1.0, 0.0]}
    visits = {_key("BB", "s4:4", 0): 10, _key("BB", "s6:6", 0): 1, _key("BB", "s4:4", 1): 1, _key("SB", "s4:4", 3): 5}
    kept = {k: r for k, r in before.items() if visits.get(k, 0) >= 5}
    fit_rows = W._top_fit(before, kept, visits, 100, 10_000)[3]
    have = {(ck, m) for ck, by_m in W._l1_rows(kept).items() for m in by_m}
    shipped = {(ck, m) for ck, by_m in fit_rows.items() for m in by_m}
    want = {(ck, m) for ck, by_m in W._l1_rows(before).items() for m in by_m}
    assert have | shipped == want and shipped and not have & shipped
