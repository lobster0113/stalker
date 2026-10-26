import json

import pytest

from referee import metrics
from referee.evaluate import SCHEMA_VERSION, evaluate
from referee.agents.reference_bot import factory
from referee.gate_b.candidates import random_legal
from referee.gate_b.runner import INSUFFICIENT, load_spec, run_pilot
from referee.stats import required_tournaments
from stalker.tournament.config import load_preset

SMALL = {"name": "t", "reference_version": "refbot-v1+icm-ref-v1+chart-v1+post-v1+short15bb",
         "presets": ["6max_sng_wta"], "blocks": 4, "rotations": 3, "seed": 5, "delta_min": 0.1,
         "pilot_sigma": 0.6, "alpha": 0.05, "power": 0.9}
KEYS = ("roi_diff", "ci_lower", "ci_upper", "verdict", "sd_dup", "sd_indep")


def test_eval_result_v2_carries_game_diffs():
    cfg = load_preset("6max_sng_wta")
    res = evaluate(cfg, random_legal(cfg), factory(cfg.payout_ratios()), blocks=3, seed=1, rotations=2)
    d = res.to_dict()
    assert SCHEMA_VERSION == 2 and d["schema_version"] == 2
    assert [len(g) for g in d["block_game_diffs"]] == [4, 4, 4]
    for diff, games in zip(res.block_diffs, res.block_game_diffs):
        assert diff == pytest.approx(sum(games) / len(games))


def test_pilot_keys_and_determinism():
    a = metrics.gate_b_pilot(SMALL)
    assert a == metrics.gate_b_pilot(SMALL)
    _, sha = load_spec(metrics.GATE_B_PILOT_SPEC)
    assert a["gate_b_pilot_spec_sha256"] == sha
    for k in KEYS:
        assert f"gate_b_pilot_6max_sng_wta_{k}" in a
    assert a["gate_b_pilot_6max_sng_wta_verdict"] == INSUFFICIENT  # 4 blocks < required(0.6, 0.1)
    sd = a["gate_b_pilot_6max_sng_wta_sd_dup"]
    assert sd > 0 and a["gate_b_pilot_required_tournaments"] == required_tournaments(sd, 0.1)
    json.dumps(a)  # must be appendable to history.jsonl


def test_reference_vs_reference_ci_contains_zero():
    out = run_pilot(SMALL, "x", "referee.gate_b.candidates:reference")
    k = "gate_b_pilot_6max_sng_wta"
    assert out[f"{k}_ci_lower"] <= 0 <= out[f"{k}_ci_upper"]
    # The reference bot ignores its rng, so duplicate mirrors it exactly; unpaired, the noise is visible.
    assert out[f"{k}_sd_dup"] == 0 and out[f"{k}_sd_indep"] > 0
    assert out["gate_b_pilot_required_tournaments"] == 2


def test_pilot_spec_file_is_fixed():
    spec, _ = load_spec(metrics.GATE_B_PILOT_SPEC)
    assert spec["presets"] == ["6max_sng_wta", "9max_sng_503020"]
    assert spec["blocks"] < required_tournaments(spec["pilot_sigma"], spec["delta_min"])  # a pilot, not a verdict


@pytest.mark.slow
def test_real_pilot_random_legal_loses():
    snap = metrics.gate_b_pilot()
    for preset in ("6max_sng_wta", "9max_sng_503020"):
        k = f"gate_b_pilot_{preset}"
        assert snap[f"{k}_roi_diff"] < 0 and snap[f"{k}_ci_upper"] < 0, preset
