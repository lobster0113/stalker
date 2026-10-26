import hashlib
import json

import pytest

from referee.gate_a.__main__ import main
from referee.gate_a.runner import (FAIL, PARTIAL, PASS, SPEC_V1, load_spec, overall_verdict, run_gate_a)
from referee.gate_a.spots import SPOTS_V1, spot_set_hash

C = "referee.gate_a.candidates:"
# Two cheap 6-max non-bubble spots; a loose baseline tol keeps the quick tests fast.
SUBSET_IDS = ("6n-push-btn-10bb", "6n-call-bb-vs-sb-15bb")


@pytest.fixture
def subset(tmp_path):
    spots = [s for s in json.loads(SPOTS_V1.read_text())["spots"] if s["id"] in SUBSET_IDS]
    sp = tmp_path / "spots.json"
    sp.write_text(json.dumps({"spots": spots}))
    spec = {**json.loads(SPEC_V1.read_text()), "spot_set_sha256": hashlib.sha256(sp.read_bytes()).hexdigest(),
            "baseline_tol": 1e-3, "n_boot": 500}
    pp = tmp_path / "spec.json"
    pp.write_text(json.dumps(spec))
    return sp, pp


def test_default_spec_pins_v1_spot_set_and_gates_md_deltas():
    spec, sha = load_spec()
    assert len(sha) == 64
    assert (spec["spot_set_version"], spec["spot_set_sha256"]) == spot_set_hash(SPOTS_V1)
    gates = open("referee/GATES.md", encoding="utf-8").read()
    assert f"δ_ni = {spec['delta_ni']}" in gates and f"δ_min = {spec['delta_min']}" in gates
    assert spec["baseline"] == "reference" and spec["baseline_tol"] <= spec["delta_ni"] / 5


def test_spec_errors(tmp_path, subset):
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    with pytest.raises(ValueError, match="lacks"):
        load_spec(bad)
    spec, sha = load_spec(SPEC_V1)
    with pytest.raises(ValueError, match="pins"):
        run_gate_a(spec, sha, C + "reference", subset[0])
    with pytest.raises(ValueError, match="module:factory"):
        run_gate_a(*load_spec(subset[1]), "referee.gate_a.candidates", subset[0])


def test_overall_verdict_is_per_format():
    assert overall_verdict([PASS, PASS]) == PASS
    assert overall_verdict([PASS, FAIL]) == PARTIAL
    assert overall_verdict([FAIL, FAIL]) == FAIL
    assert overall_verdict([]) == FAIL


def test_reference_candidate_is_noninferior_not_superior(subset):
    spec, sha = load_spec(subset[1])
    res = run_gate_a(spec, sha, C + "reference", subset[0])
    f = res["formats"]["6max-nonbubble"]
    assert f["nash_noninferiority"]["passed"] and not f["pool_superiority"]["passed"]
    assert res["verdict"] == FAIL and res["baseline"] == "reference" and res["spec_sha256"] == sha
    assert all(r["nash"] == 0 and set(r["pool"].values()) == {0} for r in res["spots"])


def test_always_push_fails_nash_noninferiority(subset):
    res = run_gate_a(*load_spec(subset[1]), C + "always_push", subset[0])
    assert not res["formats"]["6max-nonbubble"]["nash_noninferiority"]["passed"]


def test_cli_outputs_are_byte_identical(tmp_path, subset):
    outs = []
    for k in range(2):
        out = tmp_path / f"o{k}"
        rc = main(["--spots", str(subset[0]), "--spec", str(subset[1]), "--candidate", C + "top_percent",
                   "--out", str(out)])
        outs.append(((out / "gate_a.json").read_bytes(), (out / "gate_a.md").read_bytes()))
    res = json.loads(outs[0][0])
    assert outs[0] == outs[1] and rc == (0 if res["verdict"] == PASS else 1)
    assert res["schema_version"] == 1 and "참조기 기준" in outs[0][1].decode()


@pytest.mark.slow
def test_v1_reference_and_trivial_candidates():
    spec, sha = load_spec()
    ref = run_gate_a(spec, sha, C + "reference", SPOTS_V1)
    assert set(ref["formats"]) == {"6max-bubble", "6max-nonbubble", "9max-bubble", "9max-nonbubble"}
    for f in ref["formats"].values():
        assert f["nash_noninferiority"]["passed"] and not f["pool_superiority"]["passed"]
    for cand in ("always_fold", "always_push"):
        res = run_gate_a(spec, sha, C + cand, SPOTS_V1)
        assert res["verdict"] == FAIL
        assert not any(f["nash_noninferiority"]["passed"] for f in res["formats"].values()), cand
