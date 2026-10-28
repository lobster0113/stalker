import json

import numpy as np
import pytest

from referee import gate_s as S


@pytest.fixture(scope="module")
def spec():
    return S.load()[0]


def test_spot_set_loads_with_hash_and_enough_golden_spots():
    spec, sha = S.load()
    assert len(sha) == 64 and len(spec["golden"]) >= 5 and len(spec["base"]) == 116


def test_perturbations_stay_in_the_stack_bucket_and_are_seeded(spec):
    ps = S.pairs(spec)
    assert ps == S.pairs(spec)
    edges = spec["bucket_edges"]
    assert all(S._bucket(a, edges) == S._bucket(b, edges) and a != b for _, _, a, b in ps)


def test_bad_spot_files_are_rejected(tmp_path, spec):
    few = tmp_path / "few.json"
    few.write_text(json.dumps({**spec, "golden": spec["golden"][:4]}), encoding="utf-8")
    with pytest.raises(S.SpotError, match="at least 5"):
        S.load(few)
    cross = tmp_path / "cross.json"
    cross.write_text(json.dumps({**spec, "golden": [{**spec["golden"][0], "b": 7.0}] + spec["golden"][1:]}), encoding="utf-8")
    with pytest.raises(S.SpotError, match="crosses a bucket edge"):
        S.load(cross)


def test_the_nash_anchor_passes(spec):
    r = S.evaluate(S.nash_policy, spec)
    assert r["passed"], r["fails"]


def test_a_policy_oversensitive_to_the_raw_stack_fails_on_tv(spec):
    r = S.evaluate(S.oversensitive_policy, spec)
    assert not r["passed"] and any(f.startswith("tv p95") for f in r["fails"])


def test_a_flattened_policy_fails_on_the_golden_spots(spec):
    r = S.evaluate(S.flat_policy, spec)
    assert r["tv_p95"] == 0.0 and not any(g["ok"] for g in r["golden"])
    assert any("too flat" in f for f in r["fails"])


def test_tp_change_is_measured_in_scale_steps(spec):
    def jumpy(seat, stack, ante):
        probs, _ = S.nash_policy(seat, stack, ante)
        return probs, np.full(169, int(stack))         # the TP value moves with every BB of stack

    r = S.evaluate(jumpy, spec)
    assert r["tp_change_p95"] > 1 and any(f.startswith("tp change") for f in r["fails"])


def _nash_with_bins(step_points, jump):
    def policy(seat, stack, ante):
        return S.nash_policy(seat, stack, ante)[0], np.full(169, int(stack * jump))
    if step_points is not None:
        policy.tp_step_points = step_points
    return policy


def test_tp_change_tolerance_is_the_larger_of_one_step_and_the_fixed_point_width(spec):
    # moves ~one bin per BB of stack: p95 well above one step, so a coarse scale (25 points) is judged
    # in steps and fails, while a fine scale (1 point) is judged in points: p95 steps * 1 <= 10 passes
    assert any(f.startswith("tp change") for f in S.evaluate(_nash_with_bins(None, 1), spec)["fails"])
    assert any(f.startswith("tp change") for f in S.evaluate(_nash_with_bins(25, 1), spec)["fails"])
    fine = S.evaluate(_nash_with_bins(1, 1), spec)
    assert fine["tp_change_p95_points"] == fine["tp_change_p95"] and fine["tp_change_p95"] <= 10
    assert not any(f.startswith("tp change") for f in fine["fails"])
    wide = S.evaluate(_nash_with_bins(1, 6), spec)      # the same policy jumping 6x as far on the fine scale
    assert wide["tp_change_p95_points"] > 10 and any(f.startswith("tp change") for f in wide["fails"])


def test_the_point_width_keeps_the_discrimination_policies_failing(spec):
    # the tolerance only touches the TP-change criterion; tv and golden keep failing the bad policies
    assert S.evaluate(S.nash_policy, spec)["passed"]
    assert not S.evaluate(S.oversensitive_policy, spec)["passed"]
    assert not S.evaluate(S.flat_policy, spec)["passed"]


def test_policy_output_is_validated(spec):
    with pytest.raises(ValueError, match="169 probabilities"):
        S.evaluate(lambda seat, stack, ante: (np.full(10, 0.5), None), spec)


@pytest.mark.slow
def test_e1_tp_policy_is_evaluated(spec):
    from stalker.e1.tp_pushfold import gate_s_policy

    r = S.evaluate(gate_s_policy("mid", "quantile", iters=300), spec)
    assert r["pairs"] == len(S.pairs(spec)) and r["tp_change_p95"] is not None and len(r["golden"]) == len(spec["golden"])


def test_tv_is_reported_per_seat(spec):
    r = S.evaluate(S.oversensitive_policy, spec)
    assert set(r["tv_p95_by_seat"]) == {"sb", "bb"} and all(0 <= v <= 1 for v in r["tv_p95_by_seat"].values())
    assert max(r["tv_p95_by_seat"].values()) >= r["tv_p95"] - 1e-9


def test_check_mode_is_the_gates_full_step():
    import subprocess
    import sys

    from referee.gates import FULL_CHECKS

    assert ("gate_s", [sys.executable, "-m", "referee.gate_s", "--check"]) in FULL_CHECKS
    r = subprocess.run([sys.executable, "-m", "referee.gate_s", "--check"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr


def test_check_mode_fails_when_discrimination_is_lost(monkeypatch):
    from referee.gate_s import __main__ as cli

    monkeypatch.setattr(S, "flat_policy", S.nash_policy)
    assert cli.check() == 1
