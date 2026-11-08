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
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
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
    res = json.loads(a.read_text())
    assert res["rows"][0]["hands"] == 3 and "by_players" not in res and res["backoff"]["off"]["2"]["seeds"] == [1]


def test_job_spec_passes_the_launcher_dry_run(tmp_path):
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    job = launcher.parse_spec((ROOT / "jobs/web-policy-lbr-mid.yaml").read_text(), "jobs/web-policy-lbr-mid.yaml")
    assert job.result_path and "web_policy_lbr_job" in job.command
    assert job.hourly_usd * job.max_minutes / 60 <= 5.0
