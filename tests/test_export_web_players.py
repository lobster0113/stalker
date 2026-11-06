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
