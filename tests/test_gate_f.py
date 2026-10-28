import json
import subprocess
import sys

import numpy as np
import pytest

from referee import gate_f as F
from referee.anchors import pushfold as P
from stalker.e1 import tp_pushfold as T

SPOT = (10.0, 0.0)


@pytest.fixture(scope="module", params=["quantile", "uniform"])
def scale(request):
    return request.param


@pytest.fixture(scope="module")
def policy(scale):
    return T.gate_f_policy("beginner", scale, iters=600)


def test_spec_reproduces_the_trained_policy(policy, scale):
    r = T.train(*SPOT, "beginner", 600, "called", scale)
    assert np.array_equal(policy("sb", *SPOT).probs(), r.push)
    assert np.array_equal(policy("bb", *SPOT).probs(), r.call)


def test_bins_match_the_tier_bucketer():
    eq = T.sb_equity()
    w = P._payoffs(*SPOT)[0].sum(axis=1)
    for scale in T.SCALES:
        for tier in T.TIER_STEP:
            v, edges = T.tp_values(tier, scale, eq, w)
            assert np.array_equal(np.searchsorted(edges, v, side="right"), T._bucketer(tier, scale, w)(eq))
            assert ((edges > 0) & (edges < 100)).all()


def test_zero_error_is_the_policy_exactly(policy):
    for seat in F.SEATS:
        spec = policy(seat, *SPOT)
        assert np.array_equal(F.follow(spec, 0.0), spec.probs())
    row = F.evaluate(policy, [SPOT], "beginner", sigma=0.0)["rows"][0]
    assert row["nash_loss_added"] == 0 and row["exploitability_added"] == 0


def test_loss_does_not_fall_as_error_grows(policy):
    losses = [F.evaluate(policy, [SPOT], "beginner", sigma=s)["mean"]["nash_loss"] for s in (0.0, 6.0, 12.0, 20.0)]
    assert all(b >= a - 1e-12 for a, b in zip(losses, losses[1:])), losses
    assert losses[-1] > losses[0]


def test_bin_weights_are_distributions(policy):
    w = F.bin_weights(policy("bb", *SPOT), 20.0)
    assert (w >= 0).all() and np.allclose(w.sum(axis=1), 1.0)


def test_sampled_follower_matches_exact_mean_for_any_rho(policy):
    spec = policy("sb", *SPOT)
    exact = F.follow(spec, 20.0)
    deals = np.repeat(np.arange(169), 400)
    for rho in (0.0, 0.8):
        got = F.sample_policy(spec, 20.0, rho, np.random.default_rng(1).permutation(deals), np.random.default_rng(2))
        assert np.abs(got - exact).max() < 0.15, rho
        assert np.abs(got - exact).mean() < 0.03, rho


def test_sampling_is_reproducible(policy):
    spec, deals = policy("sb", *SPOT), np.arange(169)
    a = F.sample_policy(spec, 12.0, 0.5, deals, np.random.default_rng(7))
    assert np.array_equal(a, F.sample_policy(spec, 12.0, 0.5, deals, np.random.default_rng(7)))


def test_unoccupied_bins_take_the_nearest_trained_action():
    spec = T.gate_f_policy("pro", "uniform", iters=300)("sb", *SPOT)
    occupied = np.unique(spec.bins(spec.values))
    top = occupied.max()
    # No hand reads above the top occupied equity bin; perceiving it must not turn a shove into a fold.
    assert (spec.bin_probs[top:] == spec.bin_probs[top]).all()


def test_nash_loss_is_zero_for_the_anchor():
    push, call = P.strategy(*SPOT)
    sb, bb = F.nash_loss(*SPOT, push, call)
    assert sb < 0.01 and bb < 0.01


def test_result_is_report_only(policy):
    res = F.evaluate(policy, [SPOT], "beginner")
    assert res["verdict"].startswith("report_only") and res["sigma"] == F.SIGMA["beginner"]


@pytest.mark.slow
def test_cli_writes_report(tmp_path):
    out = tmp_path / "f.json"
    subprocess.run([sys.executable, "-m", "referee.gate_f", "--tiers", "pro", "--stacks", "10", "--antes", "0",
                    "--out", str(out)], check=True, capture_output=True)
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["tiers"]["pro"]["spots"] == 1 and res["verdict"] == F.VERDICT
