import json
import subprocess
from pathlib import Path

import pytest

from referee import metrics
from referee.gate_l import Report


def test_gate_l_snapshot_keys_and_ranges():
    snap = metrics.gate_l()
    assert 0.0 <= snap["gate_l_pass_rate"] <= 1.0
    assert isinstance(snap["gate_l_checks"], int) and snap["gate_l_checks"] > 0
    items = snap["gate_l_items"]
    assert set(items) >= {"L1", "L3", "L4", "L5"}
    for passed, total in items.values():
        assert 0 <= passed <= total and total > 0
    assert sum(t for _, t in items.values()) == snap["gate_l_checks"]


def test_gate_l_failure_lowers_pass_rate():
    report = Report()
    report.check("L1", True, "")
    report.check("L1", False, "leak")
    report.check("L3", True, "")
    snap = metrics.gate_l(report)
    assert snap["gate_l_pass_rate"] < 1.0
    assert snap["gate_l_pass_rate"] == round(2 / 3, 6)
    assert snap["gate_l_checks"] == 3
    assert snap["gate_l_items"] == {"L1": [1, 2], "L3": [1, 1]}


def test_gate_l_empty_report_is_not_a_pass():
    assert metrics.gate_l(Report())["gate_l_pass_rate"] == 0.0


@pytest.mark.slow
def test_snapshot_includes_gate_l(monkeypatch):
    monkeypatch.setattr(metrics, "test_counts", lambda: {})
    monkeypatch.setattr(metrics, "gate_r", lambda: {})
    monkeypatch.setattr(metrics, "gate_s_e1", lambda: {})  # trains three tiers; covered by its own slow test
    monkeypatch.setattr(metrics, "e3_web_lbr", lambda: {"e3_web_lbr": None})  # reads ops; covered below
    snap = metrics.snapshot()
    assert {"gate_l_pass_rate", "gate_l_checks", "gate_l_items"} <= set(snap)


@pytest.mark.slow
def test_snapshot_has_no_retired_keys(monkeypatch):
    monkeypatch.setattr(metrics, "test_counts", lambda: {})
    monkeypatch.setattr(metrics, "gate_r", lambda: {})
    monkeypatch.setattr(metrics, "gate_s_e1", lambda: {})  # trains three tiers; covered by its own slow test
    monkeypatch.setattr(metrics, "e3_web_lbr", lambda: {"e3_web_lbr": None})  # reads ops; covered below
    snap = metrics.snapshot()
    retired = [k for k in snap if k.startswith(("gate_a_", "gate_b_", "suff_")) or k == "d1_preliminary"]
    assert not retired, retired
    assert not any(hasattr(metrics, f) for f in ("gate_a", "gate_b_pilot", "sufficiency"))


@pytest.mark.slow
def test_training_metrics_are_exact_and_deterministic():
    import time

    t0 = time.monotonic()
    a = {**metrics.e0(), **metrics.e1()}
    elapsed = time.monotonic() - t0
    assert a == {**metrics.e0(), **metrics.e1()}
    assert a["e0_kuhn_cfr_exploitability"] < 1e-3 and a["e0_leduc_cfr_exploitability"] < 1e-2
    assert a["e1_tp_pro_exploitability"] <= a["e1_tp_mid_exploitability"] <= a["e1_tp_beginner_exploitability"]
    assert a["e1_tp_beginner_exploitability"] < a["e1_tp_uniform_beginner_exploitability"]
    assert elapsed < 120, elapsed  # snapshot budget (#170): about a minute on CI


@pytest.mark.slow
def test_gate_s_record_has_types_ranges_and_is_reproducible():
    a = metrics.gate_s_e1()["gate_s_e1"]
    assert a == metrics.gate_s_e1()["gate_s_e1"]
    assert len(a["spots_sha256"]) == 64 and a["policies"]["nash_anchor"]["passed"] is True
    for name, r in a["policies"].items():
        assert 0 <= r["tv_p95_sb"] <= 1 and 0 <= r["tv_p95_bb"] <= 1, name
        assert r["golden_total"] >= 5 and 0 <= r["golden_ok"] <= r["golden_total"], name
        assert isinstance(r["passed"], bool) and r["stab_regret_p99_pct"] >= 0, name


def test_gate_f_metrics_are_deterministic_and_ordered():
    a = metrics.gate_f_e1()
    assert a == metrics.gate_f_e1()
    for tier in ("beginner", "mid", "pro"):
        assert a[f"gate_f_e1_{tier}_nash_loss"] >= a[f"gate_f_e1_{tier}_nash_loss_added"] >= 0
    # Larger human error costs more: the tiers' sigmas are 20 > 12 > 6.
    assert a["gate_f_e1_pro_nash_loss_added"] <= a["gate_f_e1_mid_nash_loss_added"] <= a["gate_f_e1_beginner_nash_loss_added"]


JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="1" failures="2" skipped="3" tests="20"></testsuite></testsuites>"""


def test_test_counts_read_the_junit_report_of_the_tests_job(tmp_path):
    (tmp_path / "junit.xml").write_text(JUNIT, encoding="utf-8")
    assert metrics.test_counts(str(tmp_path / "junit.xml")) == {"tests_passed": 14, "tests_failed": 3}


def test_test_counts_missing_junit_report_fails_loudly(tmp_path):
    with pytest.raises(SystemExit, match="METRICS_JUNIT"):
        metrics.test_counts(str(tmp_path / "none.xml"))


# The keys each part contributes, as the history rows have them; a part dropped from snapshot() fails here.
PARTS = {
    "test_counts": {"tests_passed", "tests_failed"},
    "gate_r": {"gate_r_pass_rate", "gate_r_checks", "gate_r_cash_pass_rate", "gate_r_cash_checks",
               "gate_r_e3_pass_rate", "gate_r_e3_checks"},
    "gate_l": {"gate_l_pass_rate", "gate_l_checks", "gate_l_items"},
    "gate_s_e1": {"gate_s_e1"},
    "e0": {"e0_kuhn_iters", "e0_leduc_iters", "e0_kuhn_cfr_exploitability", "e0_leduc_cfr_exploitability"},
    "e1": {"e1_stacks", "e1_iters", "e1_tp_beginner_exploitability", "e1_tp_mid_exploitability",
           "e1_tp_pro_exploitability", "e1_nash_fp_exploitability", "e1_tp_uniform_beginner_exploitability"},
    "gate_f_e1": {f"gate_f_e1_{t}_{k}" for t in ("beginner", "mid", "pro") for k in ("nash_loss", "nash_loss_added")},
    "e3_web_lbr": {"e3_web_lbr"},
}


def test_snapshot_key_set_and_stage_timings(monkeypatch, capsys):
    for name, keys in PARTS.items():
        stub = (lambda ks: lambda: dict.fromkeys(ks, 0))(keys)
        stub.__name__ = name
        monkeypatch.setattr(metrics, name, stub)
    snap = metrics.snapshot()
    assert set(snap) == {"ts", "sha", "source", "stalker_loc"}.union(*PARTS.values())
    err = capsys.readouterr().err
    for name in [*PARTS, "code_size"]:
        assert f"metrics: {name} " in err, err


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                   capture_output=True)


def _lbr_result(run_policy, lbr_on_3, pass_on_3=True):
    cell = lambda lbr, limit, ok: {"hands": 600, "lbr_bb": lbr, "lbr_stderr_bb": 0.3, "limit": limit,
                                   "pass": ok, "policy_sha256": "x", "seeds": [1, 2, 3]}
    return {"schema": "stalker.web.policy-lbr", "schema_version": 1, "policy_run": run_policy,
            "backoff": {"on": {"2": cell(5.5, 9.0, True), "3": cell(lbr_on_3, 6.4, pass_on_3)},
                        "off": {"2": cell(6.8, 9.0, True), "3": cell(4.4, 6.4, True)}},
            "rows": [], "thresholds": "referee/e3/lbr_thresholds_v2.json"}


@pytest.fixture
def ops_clone(tmp_path):
    """A clone whose origin has an ops branch with two policy-lbr results and newer unrelated ones."""
    origin = tmp_path / "origin"
    (origin / "cloud" / "results").mkdir(parents=True)
    _git(origin, "init", "-q", "-b", "ops")
    res = origin / "cloud" / "results"
    (res / "100.json").write_text(json.dumps(_lbr_result("p1", 9.9, False)), encoding="utf-8")
    (res / "200.json").write_text(json.dumps(_lbr_result("p2", 4.5)), encoding="utf-8")
    (res / "300.json").write_text(json.dumps({"schema": "stalker.cloud.other", "by_players": {}}), encoding="utf-8")
    (res / "400.summary.json").write_text(json.dumps(_lbr_result("p4", 1.0)), encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "ops")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", "--no-checkout", str(origin), str(clone))
    return origin, clone


def _pages(repo, **run_ids):
    """Write web page policies `mid-<n>.json` with the given run ids (key `p<n>`)."""
    d = repo / "web" / "app" / "policy"
    d.mkdir(parents=True, exist_ok=True)
    for key, run_id in run_ids.items():
        (d / f"mid-{key[1:]}.json").write_text(json.dumps({"schema": "stalker.web.policy", "run_id": run_id}),
                                              encoding="utf-8")


def test_e3_web_lbr_copies_the_newest_policy_lbr_result(ops_clone):
    _, clone = ops_clone
    _pages(clone, p2="p2", p3="p2")
    got = metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]
    assert got["run"] == 200 and got["policy_run"] == "p2"
    assert got["by_players"]["3"]["on"] == {"lbr_bb": 4.5, "lbr_stderr_bb": 0.3, "limit": 6.4, "pass": True}
    assert got["by_players"]["2"]["off"]["lbr_bb"] == 6.8
    assert list(got["by_players"]) == ["2", "3"]
    assert set(got["by_players"]["2"]) == {"on", "off", "page_run"}
    assert got["all_pass_on"] is True
    assert got["by_players"]["2"]["page_run"] == "p2" and got["fresh"] is True


def test_e3_web_lbr_is_stale_when_one_page_has_another_run(ops_clone):
    _, clone = ops_clone
    _pages(clone, p2="p2", p3="older", p6="older")  # 6 is not measured, so it does not count
    got = metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]
    assert got["by_players"]["3"]["page_run"] == "older"
    assert "6" not in got["by_players"]
    assert got["fresh"] is False


def test_e3_web_lbr_is_stale_when_a_page_file_is_missing(ops_clone):
    _, clone = ops_clone
    _pages(clone, p2="p2")
    (clone / "web" / "app" / "policy" / "mid-3.json").write_text("{not json", encoding="utf-8")
    got = metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]
    assert got["by_players"]["3"]["page_run"] is None and got["fresh"] is False
    (clone / "web" / "app" / "policy" / "mid-3.json").unlink()
    got = metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]
    assert got["by_players"]["3"]["page_run"] is None and got["fresh"] is False


def test_e3_web_lbr_page_run_matches_across_str_and_int(ops_clone):
    origin, clone = ops_clone
    (origin / "cloud" / "results" / "250.json").write_text(json.dumps(_lbr_result(41813684540, 4.0)),
                                                         encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "int policy run")
    _pages(clone, p2="41813684540", p3="41813684540")
    assert metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]["fresh"] is True


def test_e3_web_lbr_fetches_new_results_and_reports_failures(ops_clone):
    origin, clone = ops_clone
    (origin / "cloud" / "results" / "250.json").write_text(json.dumps(_lbr_result("p3", 7.0, False)), encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "newer")
    assert metrics.e3_web_lbr(repo=clone, fetch=False)["e3_web_lbr"]["run"] == 200
    got = metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]
    assert got["run"] == 250 and got["all_pass_on"] is False


def test_e3_web_lbr_is_null_without_ops(tmp_path):
    _git(tmp_path, "init", "-q")
    assert metrics.e3_web_lbr(repo=tmp_path) == {"e3_web_lbr": None}
    assert metrics.e3_web_lbr(repo=tmp_path / "missing") == {"e3_web_lbr": None}


def _per_player_result(runs):
    doc = _lbr_result("mixed", 4.5)
    for mode in doc["backoff"].values():
        for n, cell in mode.items():
            cell["policy_run"] = runs[n]
    return doc


def _ops_with(origin, doc):
    (origin / "cloud" / "results" / "500.json").write_text(json.dumps(doc), encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "per-player result")


def test_e3_web_lbr_fresh_compares_per_player_policy_run(ops_clone):
    origin, clone = ops_clone
    _ops_with(origin, _per_player_result({"2": "A", "3": "B"}))
    _pages(clone, p2="A", p3="B")  # mixed runs, each page equals its own measured run
    assert metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]["fresh"] is True
    _pages(clone, p3="C")
    assert metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]["fresh"] is False


def test_e3_web_lbr_old_result_without_per_player_run_uses_top_level(ops_clone):
    _, clone = ops_clone
    _pages(clone, p2="p2", p3="other")
    assert metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]["fresh"] is False
    _pages(clone, p3="p2")
    assert metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]["fresh"] is True


def test_e3_web_lbr_without_on_cell_for_a_legacy_count(ops_clone):
    """#702: a legacy page has only an off cell; fresh still compares its own run, all_pass_on looks at on cells only."""
    origin, clone = ops_clone
    doc = _per_player_result({"2": "A", "3": "B"})
    del doc["backoff"]["on"]["3"]
    _ops_with(origin, doc)
    _pages(clone, p2="A", p3="B")
    got = metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]
    assert got["fresh"] is True and got["all_pass_on"] is True and "on" not in got["by_players"]["3"]
    _pages(clone, p3="C")
    assert metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]["fresh"] is False


def test_e3_web_lbr_single_seed_three_player_cell_is_not_a_pass(ops_clone):
    # ADR 0024: 3 players need 2 seeds, so a 1-seed result carries pass=None -> all_pass_on False, metric intact
    origin, clone = ops_clone
    _pages(clone, p2="p9", p3="p9")
    _ops_with(origin, _lbr_result("p9", 4.5, None))
    got = metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]
    assert got["run"] == 500 and got["by_players"]["3"]["on"]["pass"] is None
    assert got["all_pass_on"] is False and got["fresh"] is True


def test_e3_web_lbr_reads_a_schema2_result_like_schema1(tmp_path):
    """#781: schema 2 adds aivat_* cell keys; the four verdict keys and all_pass_on are unchanged (#797 copies aivat_* on top)."""
    out = {}
    for ver in (1, 2):
        origin = tmp_path / f"o{ver}"
        (origin / "cloud" / "results").mkdir(parents=True)
        _git(origin, "init", "-q", "-b", "ops")
        doc = _lbr_result("p2", 4.5)
        if ver == 2:
            doc["schema_version"], doc["aivat_samples"] = 2, 8
            for cells in doc["backoff"].values():
                for c in cells.values():
                    c.update(aivat_lbr_bb=c["lbr_bb"] - 1, aivat_stderr_bb=0.1)
        (origin / "cloud" / "results" / "200.json").write_text(json.dumps(doc), encoding="utf-8")
        _git(origin, "add", "-A")
        _git(origin, "commit", "-qm", "ops")
        clone = tmp_path / f"c{ver}"
        _git(tmp_path, "clone", "-q", "--no-checkout", str(origin), str(clone))
        _pages(clone, p2="p2", p3="p2")
        out[ver] = metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]
    strip = lambda d: {n: {m: {k: v for k, v in c.items() if not k.startswith("aivat_")} if isinstance(c, dict) else c
                           for m, c in cells.items()} for n, cells in d["by_players"].items()}
    assert strip(out[1]) == strip(out[2]) and out[2]["all_pass_on"] is True
    assert out[2]["by_players"]["2"]["on"]["aivat_lbr_bb"] == 4.5


def test_e3_web_lbr_copies_aivat_columns_when_present(ops_clone):
    origin, clone = ops_clone
    doc = _lbr_result("p5", 4.0)
    doc["backoff"]["on"]["3"].update(aivat_lbr_bb=3.9, aivat_stderr_bb=0.1)
    _ops_with(origin, doc)
    got = metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]["by_players"]
    assert got["3"]["on"]["aivat_lbr_bb"] == 3.9 and got["3"]["on"]["aivat_stderr_bb"] == 0.1
    assert "aivat_lbr_bb" not in got["2"]["on"]


def test_e3_web_lbr_v3_judges_the_fixture(ops_clone):
    origin, clone = ops_clone
    fixture = Path(__file__).parent / "fixtures" / "web_policy_lbr_43111293721.json"
    _ops_with(origin, json.loads(fixture.read_text(encoding="utf-8")))
    got = metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]
    assert {n: r["verdict"] for n, r in got["v3"].items()} == dict.fromkeys("23456", "pass")
    assert [got["v3"][n]["mean"] for n in "23456"] == [5.781, 4.677, 2.646, 1.950, 0.766]
    assert got["all_pass_v3"] is True


def test_e3_web_lbr_v3_error_for_schema_1_keeps_the_rest(ops_clone):
    origin, clone = ops_clone
    doc = _lbr_result("p6", 4.0)
    doc["rows"] = [{"players": 3, "backoff": True, "seed": 1, "hands": 2000, "lbr_bb": 4.0}]
    _ops_with(origin, doc)
    got = metrics.e3_web_lbr(repo=clone)["e3_web_lbr"]
    assert "aivat_lbr_bb" in got["v3"]["error"] and got["all_pass_v3"] is None
    assert got["run"] == 500 and got["all_pass_on"] is True


def test_all_pass_v3_rolls_up_fail_and_insufficient():
    row = lambda n, a: {"players": n, "backoff": True, "seed": 1, "hands": 2000, "lbr_bb": a, "aivat_lbr_bb": a}
    base = {"schema": "stalker.web.policy-lbr", "legacy_pages": []}
    fail = metrics._web_lbr_v3({**base, "rows": [row(2, 99.0)]})
    assert fail[0]["2"]["verdict"] == "fail" and fail[1] is False
