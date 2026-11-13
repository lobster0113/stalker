"""#661: the cloud job that measures filtered web policies at ADR 0020's hands and seeds."""
import io
import json
import sys
import tarfile
from pathlib import Path

import numpy as np
import pytest

from referee.e3.thresholds import TABLES, load_thresholds
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.tools import export_web_policy as X
from stalker.tools import web_policy_lbr_job as J

ROOT = Path(__file__).parents[1]
V2 = load_thresholds(*TABLES["v2"])
V3 = load_thresholds(*TABLES["v3"])


def test_plan_matches_adr_0020_table():
    tasks = J.plan("r1")
    by = {}
    for t in tasks:
        by.setdefault(t["players"], []).append(t)
    assert {n: {t["hands"] for t in v} for n, v in by.items()} == {2: {2000}, 3: {2000}, 4: {600}, 5: {600}, 6: {1000}}
    table = V3["players"]
    for n, v in by.items():
        seeds = sorted({t["seed"] for t in v})
        assert seeds == list(range(1, table[str(n)]["min_seeds"]["lbr"] + 1))
        assert all(t["eval_seed"] == 10_000 + t["seed"] for t in v)
        assert {t["backoff"] for t in v} == {False, True}
    assert json.dumps(tasks) == json.dumps(J.plan("r1"))


def _tar(files):
    buf = io.BytesIO()
    with tarfile.open(None, "w:gz", fileobj=buf) as t:
        for name, data in files.items():
            ti = tarfile.TarInfo("stalker-ops/" + name)
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def test_fetch_keeps_only_the_run_directory(tmp_path):
    tb = _tar({"cloud/policies/r1/mid-2.json": b"a", "cloud/policies/r2/mid-2.json": b"b",
               "cloud/policies/r1/sub/x.json": b"c", "journal/x.jsonl": b"d"})
    J.fetch("r1", tmp_path, tarball=tb)
    assert [p.name for p in tmp_path.iterdir()] == ["mid-2.json"]
    assert (tmp_path / "mid-2.json").read_bytes() == b"a"
    with pytest.raises(SystemExit, match="no cloud/policies/zz/"):
        J.fetch("zz", tmp_path / "o", tarball=tb)


def test_summarize_mean_se_and_pass():
    rows = [{"players": 4, "seed": s, "backoff": False, "lbr_bb": v, "lbr_stderr_bb": 3.0, "policy_sha256": "x"}
            for s, v in ((1, 3.0), (2, 5.5))]
    rows += [{"players": 2, "seed": 1, "backoff": True, "lbr_bb": 9.5, "lbr_stderr_bb": 1.0, "policy_sha256": "y"}]
    s = J.summarize(rows, V2)
    c = s["off"]["4"]
    assert (c["lbr_bb"], c["limit"], c["pass"], c["seeds"], c["judged_on"]) == (4.25, 4.0, False, [1, 2], "lbr_bb")
    assert abs(c["lbr_stderr_bb"] - 2.1213) < 1e-3
    assert s["on"]["2"]["pass"] is False and "4" not in s["on"]
    rows[0]["lbr_bb"] = 1.0
    assert J.summarize(rows, V2)["off"]["4"]["pass"] is True
    assert J.summarize(rows[:1], V2)["off"]["4"]["pass"] is None   # one seed of two: not enough to judge


def test_run_end_to_end_is_byte_identical(tmp_path, monkeypatch):
    s = G.deal(np.random.default_rng(3), 2)
    rng = K.initial_ranges(2)
    public = K.public_key(s, s.to_act, "full")
    table = {}
    for v in np.unique(K.equity_steps(s, s.to_act, rng, 5)):
        if v >= 0:
            table[K.key(public, int(v))] = X.quantize(np.ones(len(G.legal(s))))
    doc = {"schema": "stalker.web.policy", "players": 2, "k": 5, "depth": "full", "q": X.Q,
           "policy": {k: v for k, v in table.items()}}
    src = tmp_path / "src"
    src.mkdir()
    (src / "mid-2.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(J, "PLAYERS", (2,))
    monkeypatch.setattr(J, "plan", lambda run, **kw: [
        {"players": 2, "seed": 1, "eval_seed": 10001, "hands": 3, "backoff": False, "file": "mid-2.json", "policy_run": run}])
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    J.run("r1", a, src=src)
    J.run("r1", b, src=src)
    assert a.read_bytes() == b.read_bytes()
    res = json.loads(a.read_text(encoding="utf-8"))
    assert res["rows"][0]["hands"] == 3 and "by_players" not in res and res["backoff"]["off"]["2"]["seeds"] == [1]


def test_job_spec_passes_the_launcher_dry_run(tmp_path):
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    job = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-mid.yaml").read_text(encoding="utf-8"), "jobs/web-policy-lbr-mid.yaml")
    assert job.result_path and "web_policy_lbr_job" in job.command
    assert job.hourly_usd * job.max_minutes / 60 <= 5.0


def test_seeds3_job_spec_differs_only_in_seeds_and_stays_under_budget():
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    base = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-mid.yaml").read_text(encoding="utf-8"), "jobs/web-policy-lbr-mid.yaml")
    s3 = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-mid-s3.yaml").read_text(encoding="utf-8"), "jobs/web-policy-lbr-mid-s3.yaml")
    assert s3.command == base.command.replace("--workers 32 --out /result/web-policy-lbr-mid.json",
                                             "--workers 32 --seeds 3 --out /result/web-policy-lbr-mid-s3.json")
    assert s3.result_path == "/result/web-policy-lbr-mid-s3.json"
    assert s3.hourly_usd * s3.max_minutes / 60 <= 3.0


def test_pages_job_spec_differs_from_s3_only_in_source_and_stays_under_budget():
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    s3 = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-mid-s3.yaml").read_text(encoding="utf-8"), "jobs/web-policy-lbr-mid-s3.yaml")
    pg = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-pages.yaml").read_text(encoding="utf-8"), "jobs/web-policy-lbr-pages.yaml")
    assert pg.command == s3.command.replace(
        "POLICY_RUN=41813684540; python3 -m stalker.tools.web_policy_lbr_job --policy-run $POLICY_RUN --workers 32 --seeds 3 "
        "--out /result/web-policy-lbr-mid-s3.json",
        "python3 -m stalker.tools.run_stages --out /result/web-policy-lbr-pages.json --stage "
        "'lbr=python3 -m stalker.tools.web_policy_lbr_job --from-pages web/app/policy --workers 32 --seeds 3 "
        "--out /result/web-policy-lbr-pages.json'")  # wrapped in run_stages (#847)
    assert pg.command != s3.command
    assert pg.result_path == "/result/web-policy-lbr-pages.json"
    for f in ("image", "vcpu", "max_minutes", "hourly_usd", "cpu_flavors", "flavor_hourly_usd", "disk_gb"):
        assert getattr(pg, f) == getattr(s3, f), f
    assert pg.hourly_usd * pg.max_minutes / 60 <= 3.0
    assert (ROOT / "web/app/policy").is_dir()   # --from-pages path is relative to the main tarball root


def _page_dir(tmp_path, runs):
    d = tmp_path / "pages"
    d.mkdir()
    for n, r in runs.items():
        (d / f"mid-{n}.json").write_text(json.dumps({"run_id": r}), encoding="utf-8")
    return d


def test_plan_from_pages_uses_each_files_run_id(tmp_path):
    runs = J.page_runs(_page_dir(tmp_path, {2: "A", 3: "A", 4: "A", 5: 7, 6: "B"}))
    assert runs == {2: "A", 3: "A", 4: "A", 5: "7", 6: "B"}
    tasks = J.plan("mixed", runs=runs)
    assert {(t["players"], t["file"], t["policy_run"]) for t in tasks} == {
        (n, f"mid-{n}.json", runs[n]) for n in J.PLAYERS}
    assert all(t["policy_run"] == "mixed" for t in J.plan("mixed"))  # old mode keeps the single run


def test_page_runs_rejects_a_missing_run_id(tmp_path):
    d = _page_dir(tmp_path, {2: "A", 3: "A", 4: "A", 5: "A"})
    with pytest.raises(SystemExit):
        J.page_runs(d)


def test_summarize_records_policy_run_per_cell_only_when_asked():
    rows = [{"players": 2, "backoff": False, "seed": 1, "lbr_bb": 1.0, "lbr_stderr_bb": 0.1,
             "policy_sha256": "x", "policy_run": "A"}]
    assert "policy_run" not in J.summarize(rows)["off"]["2"]
    assert J.summarize(rows, per_players_run=True)["off"]["2"]["policy_run"] == "A"


def _real_page(path, n, variant, run_id):
    """A tiny but loadable page: every equity step of one deal, uniform rows, in the given key layout."""
    with K.using_variant(variant):
        s = G.deal(np.random.default_rng(3), n)
        public = K.public_key(s, s.to_act, "full")
        table = {K.key(public, int(v)): X.quantize(np.ones(len(G.legal(s))))
                 for v in np.unique(K.equity_steps(s, s.to_act, K.initial_ranges(n), 5)) if v >= 0}
    doc = {"schema": "stalker.web.policy", "players": n, "k": 5, "depth": "full", "q": X.Q, "run_id": run_id, "policy": table}
    if variant:
        doc["key_variant"] = variant
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_from_pages_with_a_legacy_page_skips_its_backoff_on_cells(tmp_path, monkeypatch):
    d = tmp_path / "pages"
    d.mkdir()
    _real_page(d / "mid-2.json", 2, "c1", "A")
    _real_page(d / "mid-3.json", 3, "", "B")   # pre-c1 layout, like mid-6 on main (#702)
    monkeypatch.setattr(J, "PLAYERS", (2, 3))
    real_plan = J.plan
    monkeypatch.setattr(J, "plan", lambda run, **kw: [{**t, "hands": 3} for t in real_plan(run, **kw) if t["seed"] == 1])
    out = tmp_path / "o.json"
    res = J.run(None, out, workers=1, pages=d)
    assert res["legacy_pages"] == [3]
    assert set(res["backoff"]["off"]) == {"2", "3"} and set(res["backoff"]["on"]) == {"2"}
    assert res["backoff"]["on"]["2"]["policy_run"] == "A" and res["backoff"]["off"]["3"]["policy_run"] == "B"
    first = out.read_bytes()
    J.run(None, out, workers=1, pages=d)
    assert out.read_bytes() == first


def test_plan_legacy_players_get_off_tasks_only():
    tasks = J.plan("r", legacy=[6])
    assert {t["backoff"] for t in tasks if t["players"] == 6} == {False}
    assert {t["backoff"] for t in tasks if t["players"] == 5} == {False, True}


def test_s4long_job_spec_differs_only_in_policy_run_and_stays_under_budget():
    # #708: the 120k policies #714 re-exported; everything else must match the #669 job so the tables compare.
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    base = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-mid.yaml").read_text(encoding="utf-8"), "jobs/web-policy-lbr-mid.yaml")
    s4 = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-mid-s4long.yaml").read_text(encoding="utf-8"),
                             "jobs/web-policy-lbr-mid-s4long.yaml")
    assert "POLICY_RUN=42591543123;" in s4.command
    assert s4.command == base.command.replace("POLICY_RUN=41813684540;", "POLICY_RUN=42591543123;").replace(
        "/result/web-policy-lbr-mid.json", "/result/web-policy-lbr-mid-s4long.json")
    assert s4.result_path == "/result/web-policy-lbr-mid-s4long.json"
    for f in ("image", "vcpu", "max_minutes", "hourly_usd", "cpu_flavors", "flavor_hourly_usd", "disk_gb"):
        assert getattr(s4, f) == getattr(base, f), f
    assert s4.hourly_usd * s4.max_minutes / 60 <= 3.0


def test_evalnoise_job_spec_four_eval_seeds_backoff_off_under_budget():
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    pg = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-pages.yaml").read_text(encoding="utf-8"), "jobs/web-policy-lbr-pages.yaml")
    en = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-pages-evalnoise.yaml").read_text(encoding="utf-8"),
                             "jobs/web-policy-lbr-pages-evalnoise.yaml")
    assert en.command == pg.command.replace("--seeds 3 ", "--seeds 4 --backoff off ").replace(
        "web-policy-lbr-pages.json", "web-policy-lbr-pages-evalnoise.json")
    assert en.result_path == "/result/web-policy-lbr-pages-evalnoise.json"
    for f in ("image", "vcpu", "max_minutes", "hourly_usd", "cpu_flavors", "flavor_hourly_usd", "disk_gb"):
        assert getattr(en, f) == getattr(pg, f), f
    assert en.hourly_usd * en.max_minutes / 60 <= 3.0


def test_evalnoise_both_job_spec_same_as_evalnoise_but_backoff_both_under_budget():
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    en = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-pages-evalnoise.yaml").read_text(encoding="utf-8"),
                             "jobs/web-policy-lbr-pages-evalnoise.yaml")
    both = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-pages-evalnoise-both.yaml").read_text(encoding="utf-8"),
                               "jobs/web-policy-lbr-pages-evalnoise-both.yaml")
    assert both.command == en.command.replace("--backoff off", "--backoff both").replace(
        "evalnoise.json", "evalnoise-both.json")
    assert both.result_path == "/result/web-policy-lbr-pages-evalnoise-both.json"
    for f in ("image", "vcpu", "max_minutes", "hourly_usd", "cpu_flavors", "flavor_hourly_usd", "disk_gb"):
        assert getattr(both, f) == getattr(en, f), f
    assert both.hourly_usd * both.max_minutes / 60 <= 3.0


def test_evalnoise8_job_spec_same_as_evalnoise_both_but_eight_seeds_under_budget():
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    both = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-pages-evalnoise-both.yaml").read_text(encoding="utf-8"),
                               "jobs/web-policy-lbr-pages-evalnoise-both.yaml")
    e8 = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-pages-evalnoise8.yaml").read_text(encoding="utf-8"),
                             "jobs/web-policy-lbr-pages-evalnoise8.yaml")
    assert e8.command == both.command.replace("--seeds 4", "--seeds 8").replace(
        "evalnoise-both.json", "evalnoise8.json")
    assert e8.result_path == "/result/web-policy-lbr-pages-evalnoise8.json"
    for f in ("image", "vcpu", "max_minutes", "hourly_usd", "cpu_flavors", "flavor_hourly_usd", "disk_gb"):
        assert getattr(e8, f) == getattr(both, f), f
    assert e8.hourly_usd * e8.max_minutes / 60 <= 3.0


def test_plan_seeds_4_gives_four_distinct_eval_seeds_per_player_count_backoff_off():
    tasks = J.plan("r1", backoffs=(False,), seeds=4)
    for n in {t["players"] for t in tasks}:
        ev = [t["eval_seed"] for t in tasks if t["players"] == n]
        assert sorted(ev) == [10001, 10002, 10003, 10004]
    assert {t["backoff"] for t in tasks} == {False}


def test_main_backoff_off_runs_no_backoff_on_cells(monkeypatch):
    seen = {}
    monkeypatch.setattr(J, "run", lambda *a, **kw: seen.setdefault("a", a))
    J.main(["--from-pages", "p", "--out", "o", "--backoff", "off"])
    assert seen["a"][-2:] == ((False,), J.AIVAT_SAMPLES)   # the AIVAT column is on by default (#781)
    seen.clear()
    J.main(["--from-pages", "p", "--out", "o", "--aivat-samples", "0", "--thresholds", "v2"])
    assert seen["a"][-2:] == ((False, True), 0)


def test_three_player_needs_two_seeds_under_v2():
    from stalker.tools import web_policy_lbr_job as J
    tasks = J.plan("run", V2)
    assert sorted({t["seed"] for t in tasks if t["players"] == 3}) == [1, 2]
    rows = [{**t, "lbr_bb": 4.0, "lbr_stderr_bb": 0.6, "policy_sha256": "x"} for t in tasks if t["players"] == 3 and t["seed"] == 1]
    assert J.summarize(rows, V2)["on"]["3"]["pass"] is None
    assert J.summarize(rows + [{**r, "seed": 2} for r in rows], V2)["on"]["3"]["pass"] is True


def _v1_rows():
    return [{"players": 2, "seed": s, "backoff": False, "lbr_bb": v, "lbr_stderr_bb": 1.0, "policy_sha256": "x"}
            for s, v in ((1, 6.0), (2, 8.0))]


def test_summarize_adds_aivat_cells_only_for_schema2_rows():
    v1 = J.summarize(_v1_rows(), V2)
    assert "aivat_lbr_bb" not in v1["off"]["2"]   # a schema-1 result reads back unchanged under v2
    v2 = [{**r, "aivat_lbr_bb": a, "aivat_stderr_bb": 0.5} for r, a in zip(_v1_rows(), (5.0, 6.0))]
    s = J.summarize(v2, V2)
    c = s["off"]["2"]
    assert {k: c[k] for k in v1["off"]["2"]} == v1["off"]["2"]   # v2 table: lbr_bb, pass, ... do not move
    assert (c["aivat_lbr_bb"], c["aivat_stderr_bb"]) == (5.5, round(0.5 * 2 ** 0.5 / 2, 4))
    mixed = J.summarize([v2[0], _v1_rows()[1]], V2)
    assert "aivat_lbr_bb" not in mixed["off"]["2"]   # no half-measured mean


def test_run_records_aivat_columns_and_schema_2(tmp_path, monkeypatch):
    s = G.deal(np.random.default_rng(3), 2)
    rng = K.initial_ranges(2)
    public = K.public_key(s, s.to_act, "full")
    table = {K.key(public, int(v)): X.quantize(np.ones(len(G.legal(s))))
             for v in np.unique(K.equity_steps(s, s.to_act, rng, 5)) if v >= 0}
    doc = {"schema": "stalker.web.policy", "players": 2, "k": 5, "depth": "full", "q": X.Q, "policy": table}
    src = tmp_path / "src"
    src.mkdir()
    (src / "mid-2.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(J, "PLAYERS", (2,))
    monkeypatch.setattr(J, "plan", lambda run, **kw: [
        {"players": 2, "seed": 1, "eval_seed": 10001, "hands": 3, "backoff": False, "file": "mid-2.json", "policy_run": run}])
    v2 = J.run("r1", tmp_path / "v2.json", src=src, aivat_samples=4)
    v1 = J.run("r1", tmp_path / "v1.json", src=src, aivat_samples=0, thresholds="v2")
    assert (v2["schema_version"], v2["aivat_samples"], v1["schema_version"]) == (2, 4, 1) and "aivat_samples" not in v1
    row = v2["rows"][0]
    assert {"aivat_lbr_bb", "aivat_stderr_bb"} <= set(row) and "aivat_lbr_bb" not in v1["rows"][0]
    assert {k: row[k] for k in ("lbr_bb", "lbr_stderr_bb", "policy_sha256")} == \
        {k: v1["rows"][0][k] for k in ("lbr_bb", "lbr_stderr_bb", "policy_sha256")}
    assert v2["backoff"]["off"]["2"]["aivat_lbr_bb"] == row["aivat_lbr_bb"]
    assert J.SCHEMA_VERSION == 2 and J.AIVAT_SAMPLES == 8


# #798: the job reads table v3 (ADR 0025): one seed per cell, pass on the AIVAT-corrected column.

def test_plan_v3_default_one_seed_per_cell_and_seeds_n_gives_1_to_n():
    tasks = J.plan("r1")
    assert {(t["players"], t["backoff"]): t["seed"] for t in tasks} == {(n, b): 1 for n in J.PLAYERS for b in (False, True)}
    assert len(tasks) == 2 * len(J.PLAYERS)
    assert {t["seed"] for t in J.plan("r1", seeds=3)} == {1, 2, 3}
    assert all(V3["players"][str(n)]["min_seeds"]["lbr"] == 1 for n in J.PLAYERS)


def test_summarize_v3_service_cells_of_run_43111293721_all_pass_on_the_aivat_column():
    doc = json.loads((ROOT / "tests/fixtures/web_policy_lbr_43111293721.json").read_text(encoding="utf-8"))
    # the fixture keeps the judged keys only; se and sha are not read by the verdict
    rows = [{"lbr_stderr_bb": 0.0, "aivat_stderr_bb": 0.0, "policy_sha256": "x", **r} for r in doc["rows"]]
    s = J.summarize(rows)
    service = {**{str(n): s["on"][str(n)] for n in (2, 3, 4, 5)}, "6": s["off"]["6"]}   # 6p is a legacy page
    assert doc["legacy_pages"] == [6] and "6" not in s["on"]
    for n, c in service.items():
        assert (c["pass"], c["judged_on"]) == (True, "aivat_lbr_bb"), n
        assert "lbr_bb" in c and "lbr_stderr_bb" in c
    assert [round(service[str(n)]["aivat_lbr_bb"], 3) for n in (2, 3, 4, 5, 6)] == [5.781, 4.677, 2.646, 1.95, 0.766]   # ADR 0025


def test_summarize_v3_without_the_aivat_column_is_an_error_not_a_verdict():
    s = J.summarize(_v1_rows())
    c = s["off"]["2"]
    assert c["pass"] is None and c["error"] == "aivat_lbr_bb missing; rerun with --aivat-samples 8"
    assert "judged_on" not in c and c["lbr_bb"] == 7.0 and "lbr_stderr_bb" in c
    # judged on the corrected column, not lbr_bb: 7.0 would pass the 2p line 9.0 either way, so lift lbr_bb over it
    rows = [{**r, "lbr_bb": 10.0, "aivat_lbr_bb": 5.0, "aivat_stderr_bb": 0.5} for r in _v1_rows()]
    c = J.summarize(rows)["off"]["2"]
    assert (c["pass"], c["judged_on"], c["lbr_bb"]) == (True, "aivat_lbr_bb", 10.0)
    assert J.summarize(rows, V2)["off"]["2"]["pass"] is False


def test_run_v3_with_aivat_samples_0_is_refused_before_measuring(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "plan", lambda *a, **kw: pytest.fail("measured before refusing"))
    with pytest.raises(ValueError, match="--aivat-samples 8"):
        J.run("r1", tmp_path / "o.json", src=tmp_path, aivat_samples=0)
    assert not (tmp_path / "o.json").exists()
    with pytest.raises(SystemExit):
        J.main(["--policy-run", "r1", "--out", str(tmp_path / "o.json"), "--src", str(tmp_path), "--aivat-samples", "0"])


def test_run_result_names_the_v3_table(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "plan", lambda run, **kw: [])
    monkeypatch.setattr(J, "fetch", lambda *a: None)
    res = J.run("r1", tmp_path / "o.json")
    assert res["thresholds"] == "referee/e3/lbr_thresholds_v3.json"
    assert J.run("r1", tmp_path / "p.json", thresholds="v2")["thresholds"] == "referee/e3/lbr_thresholds_v2.json"


@pytest.mark.parametrize("name,flags", [
    ("web-policy-lbr-pages", ["--workers 32", "--seeds 3"]),
    ("web-policy-lbr-pages-evalnoise", ["--workers 32", "--seeds 4", "--backoff off"]),
    ("web-policy-lbr-pages-evalnoise8", ["--workers 32", "--seeds 8", "--backoff both"]),
    ("web-policy-lbr-pages-evalnoise-both", ["--workers 32", "--seeds 4", "--backoff both"]),
])
def test_lbr_pages_jobs_run_under_run_stages(name, flags):
    """#847: a failing measurement is retrieved as stage-failure JSON instead of being lost with the pod."""
    import shlex
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    path = f"jobs/{name}.yaml"
    job = launcher.parse_spec((ROOT / path).read_text(encoding="utf-8"), path)
    wrapped = job.command.split("; ")[-1]
    argv = shlex.split(wrapped)
    assert argv[:3] == ["python3", "-m", "stalker.tools.run_stages"], "wrap the measurement in run_stages"
    assert argv[argv.index("--out") + 1] == job.result_path
    stage = argv[argv.index("--stage") + 1]
    assert stage.startswith("lbr=python3 -m stalker.tools.web_policy_lbr_job --from-pages web/app/policy ")
    for f in flags:
        assert f in stage, f
    assert f"--out {job.result_path}" in stage
