import hashlib
import json

import pytest

from referee.gate_a.runner import SPEC_V1, load_spec
from referee.gate_a.spots import SPOTS_V1

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
    monkeypatch.setattr(metrics, "gate_a", lambda: {})
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


def _fake_result(verdict, los):
    return {"verdict": verdict, "formats": {f"f{i}": {"nash_noninferiority": {"lo": lo}} for i, lo in enumerate(los)}}


def test_gate_a_keys_from_injected_results():
    snap = metrics.gate_a({"reference": _fake_result("pass", [0.0, -0.0012344]),
                           "always_fold": _fake_result("fail", [-0.2, -0.1])})
    assert snap == {"gate_a_spot_set": load_spec(SPEC_V1)[0]["spot_set_version"], "gate_a_baseline": "reference",
                    "gate_a_reference_verdict": "pass", "gate_a_reference_worst_ni_lower": -0.001234,
                    "gate_a_always_fold_verdict": "fail", "gate_a_always_fold_worst_ni_lower": -0.2}


@pytest.fixture
def gate_a_subset(tmp_path):
    # Two cheap spots keep this test to seconds; the full v1 run happens once, in snapshot(), not in the suite.
    spots = [s for s in json.loads(SPOTS_V1.read_text())["spots"]
             if s["id"] in ("6n-push-btn-10bb", "6n-call-bb-vs-sb-15bb")]
    sp = tmp_path / "spots.json"
    sp.write_text(json.dumps({"spots": spots}))
    spec = {**json.loads(SPEC_V1.read_text()), "spot_set_sha256": hashlib.sha256(sp.read_bytes()).hexdigest(),
            "baseline_tol": 1e-3, "n_boot": 500}
    pp = tmp_path / "spec.json"
    pp.write_text(json.dumps(spec))
    return pp, sp


def test_gate_a_subset_discriminates_and_is_deterministic(gate_a_subset):
    first = metrics.gate_a(spec_file=gate_a_subset[0], spots_file=gate_a_subset[1])
    # The reference is its own baseline (diff 0 everywhere), so it is non-inferior but can never be superior to
    # itself: its verdict is "fail" by design (tests/test_gate_a.py). Discrimination is therefore read from the
    # non-inferiority bound: reference clears -delta_ni, always_fold does not.
    delta_ni = load_spec(SPEC_V1)[0]["delta_ni"]
    assert first["gate_a_reference_worst_ni_lower"] > -delta_ni
    assert first["gate_a_always_fold_verdict"] != "pass"
    assert first["gate_a_always_fold_worst_ni_lower"] < -delta_ni
    assert metrics.gate_a(spec_file=gate_a_subset[0], spots_file=gate_a_subset[1]) == first