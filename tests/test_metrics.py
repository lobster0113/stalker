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


def test_snapshot_includes_gate_l(monkeypatch):
    monkeypatch.setattr(metrics, "test_counts", lambda: {})
    monkeypatch.setattr(metrics, "gate_r", lambda: {})
    monkeypatch.setattr(metrics, "gate_s_e1", lambda: {})  # trains three tiers; covered by its own slow test
    snap = metrics.snapshot()
    assert {"gate_l_pass_rate", "gate_l_checks", "gate_l_items"} <= set(snap)


def test_snapshot_has_no_retired_keys(monkeypatch):
    monkeypatch.setattr(metrics, "test_counts", lambda: {})
    monkeypatch.setattr(metrics, "gate_r", lambda: {})
    monkeypatch.setattr(metrics, "gate_s_e1", lambda: {})  # trains three tiers; covered by its own slow test
    snap = metrics.snapshot()
    retired = [k for k in snap if k.startswith(("gate_a_", "gate_b_", "suff_")) or k == "d1_preliminary"]
    assert not retired, retired
    assert not any(hasattr(metrics, f) for f in ("gate_a", "gate_b_pilot", "sufficiency"))


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
