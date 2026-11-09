"""#661: the cloud job that measures filtered web policies at ADR 0020's hands and seeds."""
import io
import json
import sys
import tarfile
from pathlib import Path

import numpy as np
import pytest

from referee.e3.thresholds import load_thresholds
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.tools import export_web_policy as X
from stalker.tools import web_policy_lbr_job as J

ROOT = Path(__file__).parents[1]


def test_plan_matches_adr_0020_table():
    tasks = J.plan("r1")
    by = {}
    for t in tasks:
        by.setdefault(t["players"], []).append(t)
    assert {n: {t["hands"] for t in v} for n, v in by.items()} == {2: {2000}, 3: {2000}, 4: {600}, 5: {600}, 6: {1000}}
    table = load_thresholds()["players"]
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
    s = J.summarize(rows)
    c = s["off"]["4"]
    assert (c["lbr_bb"], c["limit"], c["pass"], c["seeds"]) == (4.25, 4.0, False, [1, 2])
    assert abs(c["lbr_stderr_bb"] - 2.1213) < 1e-3
    assert s["on"]["2"]["pass"] is False and "4" not in s["on"]
    rows[0]["lbr_bb"] = 1.0
    assert J.summarize(rows)["off"]["4"]["pass"] is True
    assert J.summarize(rows[:1])["off"]["4"]["pass"] is None   # one seed of two: not enough to judge


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
        "python3 -m stalker.tools.web_policy_lbr_job --from-pages web/app/policy --workers 32 --seeds 3 "
        "--out /result/web-policy-lbr-pages.json")
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
