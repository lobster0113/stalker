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
    monkeypatch.setattr(metrics, "sufficiency", lambda: {})
    monkeypatch.setattr(metrics, "gate_b_pilot", lambda: {"gate_b_pilot_spec_sha256": "x"})
    snap = metrics.snapshot()
    assert "gate_b_pilot_spec_sha256" in snap
    assert {"gate_l_pass_rate", "gate_l_checks", "gate_l_items"} <= set(snap)


def _cell(s1, s4, s5):
    return {"s1": s1, "s4": s4, "s5": s5, "lessonable": s1 and s4 and s5}


def test_sufficiency_rates_from_report():
    cells = [_cell(True, True, True), _cell(True, False, True), _cell(False, False, False), _cell(True, True, False)]
    report = {"cells": cells, "summary": {"lessonable_cells": 1,
                                          "d1_preliminary": {"lessonable_decision_share": 0.25}}}
    snap = metrics.sufficiency(report)
    assert snap == {"suff_cells": 4, "suff_lessonable_cells": 1, "suff_s1_rate": 0.75, "suff_s4_rate": 0.5,
                    "suff_s5_rate": 0.5, "d1_preliminary": 0.25}


def test_sufficiency_empty_dataset_is_not_a_pass():
    report = {"cells": [], "summary": {"lessonable_cells": 0, "d1_preliminary": {"lessonable_decision_share": 0.0}}}
    snap = metrics.sufficiency(report)
    assert snap["suff_cells"] == 0 and snap["suff_s1_rate"] == snap["suff_s4_rate"] == snap["suff_s5_rate"] == 0.0
    assert snap["d1_preliminary"] == 0.0


def test_sufficiency_real_dataset_keys_and_ranges(monkeypatch):
    monkeypatch.setattr(metrics, "SUFFICIENCY_GAMES", 4)
    snap = metrics.sufficiency()
    assert isinstance(snap["suff_cells"], int) and snap["suff_cells"] > 0
    assert isinstance(snap["suff_lessonable_cells"], int) and snap["suff_lessonable_cells"] <= snap["suff_cells"]
    for k in ("suff_s1_rate", "suff_s4_rate", "suff_s5_rate", "d1_preliminary"):
        assert 0.0 <= snap[k] <= 1.0
