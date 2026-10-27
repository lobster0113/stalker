import json

import pytest

from referee.gate_b.__main__ import main
from referee.gate_b.runner import FAIL, INSUFFICIENT, PASS, load_spec, run_gate_b
from referee.stats import required_tournaments

# Retired metric (ADR 0008): kept for the record, run only in the full gate (#104).
pytestmark = pytest.mark.slow

SPEC = {"name": "t", "reference_version": "refbot-v1+icm-ref-v1+chart-v1+post-v1+short15bb", "presets": ["6max_sng_wta"], "blocks": 4,
        "rotations": 1, "seed": 3, "delta_min": 0.1, "pilot_sigma": 0.6, "alpha": 0.05, "power": 0.9}


def _write(tmp_path, **kw):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps({**SPEC, **kw}))
    return p


def test_spec_hash_and_missing_keys(tmp_path):
    spec, sha = load_spec(_write(tmp_path))
    assert len(sha) == 64 and spec["blocks"] == 4
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    with pytest.raises(ValueError, match="lacks"):
        load_spec(bad)


def test_default_spec_loads_and_is_sufficient():
    spec, _ = load_spec("referee/gate_b/spec_v1.json")
    assert spec["blocks"] >= required_tournaments(spec["pilot_sigma"], spec["delta_min"])


def test_small_blocks_are_insufficient_even_for_a_clear_winner(tmp_path):
    spec, sha = load_spec(_write(tmp_path))
    assert spec["blocks"] < required_tournaments(0.6, 0.1)
    res = run_gate_b(spec, sha, "referee.gate_b.candidates:reference")
    assert res["verdict"] == INSUFFICIENT and res["spec_sha256"] == sha


def test_deterministic_bytes(tmp_path):
    for name in ("a", "b"):
        assert main(["--spec", str(_write(tmp_path)), "--candidate", "referee.gate_b.candidates:random_legal",
                     "--out", str(tmp_path / name)]) == 1
    assert (tmp_path / "a/gate_b.json").read_bytes() == (tmp_path / "b/gate_b.json").read_bytes()
    assert (tmp_path / "a/gate_b.md").read_text() == (tmp_path / "b/gate_b.md").read_text()


def test_aa_is_not_pass_and_random_is_not_pass(tmp_path):
    # tiny pilot_sigma makes the blocks "sufficient", so the CI path really decides
    spec, sha = load_spec(_write(tmp_path, pilot_sigma=0.01, blocks=6))
    for cand in ("reference", "random_legal"):
        res = run_gate_b(spec, sha, f"referee.gate_b.candidates:{cand}")
        assert res["verdict"] == FAIL, cand


def test_lower_bound_between_zero_and_delta_min_passes(tmp_path, monkeypatch):
    from referee import evaluate as ev
    from referee.gate_b import runner
    from referee.stats import CI
    real = ev.evaluate

    def fake(*a, **kw):
        res = real(*a, **kw)
        ci = CI(mean=0.08, lo=0.05, hi=0.11, n_clusters=6, n_obs=6, level=0.95)
        return type(res)(**{**res.__dict__, "ci": ci})

    monkeypatch.setattr(runner, "evaluate", fake)
    spec, sha = load_spec(_write(tmp_path, pilot_sigma=0.01, blocks=6))
    assert run_gate_b(spec, sha, "referee.gate_b.candidates:random_legal")["verdict"] == PASS


def test_sufficient_blocks_random_bot_fails(tmp_path):
    # tiny pilot_sigma makes 4 blocks "sufficient", so the CI decides
    spec, sha = load_spec(_write(tmp_path, pilot_sigma=0.01, blocks=6))
    res = run_gate_b(spec, sha, "referee.gate_b.candidates:random_legal")
    assert res["presets"]["6max_sng_wta"]["verdict"] == FAIL and res["verdict"] == FAIL


def test_bad_candidate_ref():
    with pytest.raises(ValueError, match="module:factory"):
        from referee.gate_b.runner import resolve_candidate
        resolve_candidate("nocolon")
