import json
import math

import numpy as np
import pytest

from referee.evaluate import _masks, evaluate, max_rotations
from referee.stats import bootstrap_ci, noninferiority, required_tournaments, sprt, superiority
from stalker.agents.base import Action, Agent, Observation
from stalker.agents.random_agent import RandomLegalAgent
from stalker.tournament.config import load_preset


# ---- bootstrap_ci ----
def test_bootstrap_ci_brackets_mean_and_is_deterministic():
    x = np.random.default_rng(1).normal(0.3, 1.0, 400)
    a = bootstrap_ci(x, rng=np.random.default_rng(5))
    b = bootstrap_ci(x, rng=np.random.default_rng(5))
    assert a == b
    assert a.lo < a.mean < a.hi
    se = x.std(ddof=1) / math.sqrt(len(x))
    assert a.hi - a.lo == pytest.approx(2 * 1.96 * se, rel=0.1)


def test_bootstrap_ci_resamples_clusters_not_observations():
    # 20 clusters of 50 identical copies: the effective sample is 20, so the CI must be ~sqrt(50) wider.
    rng = np.random.default_rng(2)
    centres = rng.normal(0, 1, 20)
    x = np.repeat(centres, 50)
    ids = np.repeat(np.arange(20), 50)
    naive = bootstrap_ci(x, rng=np.random.default_rng(0))
    clustered = bootstrap_ci(x, ids, rng=np.random.default_rng(0))
    assert clustered.n_clusters == 20 and clustered.n_obs == 1000
    assert (clustered.hi - clustered.lo) > 5 * (naive.hi - naive.lo)


@pytest.mark.parametrize("bad", [[1.0], [1.0, float("nan")]])
def test_bootstrap_ci_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        bootstrap_ci(bad)


def test_bootstrap_ci_rejects_single_cluster():
    with pytest.raises(ValueError, match="2 clusters"):
        bootstrap_ci([1.0, 2.0, 3.0], ["a", "a", "a"])


def _type1_rate(test, reps=1000, k=60, seed=11):
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(reps):
        hits += test(rng.standard_t(5, k), rng)
    return hits / reps


@pytest.mark.slow
def test_superiority_type1_error_at_most_6pct():
    # True mean 0 (heavy-tailed t5 data): a superiority pass is a false positive.
    rate = _type1_rate(lambda x, rng: superiority(x, n_boot=1000, rng=rng).passed)
    assert rate <= 0.06


@pytest.mark.slow
def test_noninferiority_type1_error_at_most_6pct():
    # True mean exactly at the margin -delta: a pass is a false positive.
    rate = _type1_rate(lambda x, rng: noninferiority(x - 0.2, delta_ni=0.2, n_boot=1000, rng=rng).passed)
    assert rate <= 0.06


def test_superiority_power_at_planned_sample_size():
    sigma, delta = 1.0, 0.4
    n = required_tournaments(sigma, delta)
    rng = np.random.default_rng(3)
    passed = [superiority(rng.normal(delta, sigma, n), n_boot=1000, rng=rng).passed for _ in range(200)]
    assert np.mean(passed) >= 0.85


def test_superiority_requires_lower_bound_above_delta_min():
    x = np.random.default_rng(4).normal(1.0, 0.5, 200)
    assert superiority(x).passed
    assert not superiority(x, delta_min=1.5).passed


def test_noninferiority_passes_equal_and_fails_clearly_worse():
    rng = np.random.default_rng(6)
    assert noninferiority(rng.normal(0, 1, 2000), delta_ni=0.2).passed
    assert not noninferiority(rng.normal(-0.5, 1, 2000), delta_ni=0.2).passed


# ---- SPRT ----
@pytest.mark.slow
def test_sprt_type1_error_and_power():
    rng = np.random.default_rng(7)
    h0 = [sprt(rng.normal(0, 1, 2000), 0.0, 0.25, 1.0).decision for _ in range(1000)]
    h1 = [sprt(rng.normal(0.25, 1, 2000), 0.0, 0.25, 1.0).decision for _ in range(1000)]
    assert h0.count("accept_h1") / 1000 <= 0.06
    assert h1.count("accept_h1") / 1000 >= 0.85
    # SPRT is futility-only, so the error that matters is stopping a real improvement (H1) as accept_h0.
    assert h1.count("accept_h0") / 1000 <= 0.12


def test_sprt_decides_early_and_reports_continue():
    r = sprt([5.0] * 10, 0.0, 1.0, 1.0)
    assert r.decision == "accept_h1" and r.n < 10
    r = sprt([-5.0] * 10, 0.0, 1.0, 1.0)
    assert r.decision == "accept_h0"
    r = sprt([0.5], 0.0, 1.0, 1.0)
    assert r.decision == "continue" and r.n == 1


def test_sprt_rejects_bad_parameters():
    with pytest.raises(ValueError):
        sprt([0.0], 0.0, 1.0, 0.0)
    with pytest.raises(ValueError):
        sprt([0.0], 1.0, 1.0, 1.0)


# ---- sample size ----
def test_required_tournaments_formula():
    # (1.95996 + 1.28155)^2 = 10.507 -> sigma=1, delta=1 needs 11.
    assert required_tournaments(1.0, 1.0) == 11
    assert required_tournaments(2.0, 0.5) == math.ceil(10.5074 * 16)
    with pytest.raises(ValueError):
        required_tournaments(1.0, 0.0)


# ---- duplicate evaluation ----
def _random(rng):
    return RandomLegalAgent(rng)


class _Folder(Agent):
    """Folds whenever facing a bet; a clearly worse player than the random bot."""

    def act(self, obs: Observation) -> Action:
        if obs.legal.can_fold and obs.legal.call_amount > 0:
            return Action("fold")
        return Action("call")


def test_aa_random_vs_random_ci_contains_zero():
    cfg = load_preset("6max_sng_wta")
    # A fixed-seed 95% CI misses 0 for ~5% of seeds by design (seed 0 does under the contiguous mask);
    # with 400 blocks the A/A mean is within ±0.06 of 0 on both presets (local check, PR #30).
    res = evaluate(cfg, _random, _random, blocks=60, seed=1)
    assert res.ci.lo < 0 < res.ci.hi
    assert res.games == 120 and len(res.block_diffs) == 60


def test_evaluate_is_deterministic_and_records_settings():
    cfg = load_preset("9max_sng_503020")
    kw = dict(blocks=4, seed=3, rotations=2, reference_version="icm_reference v1")
    a = evaluate(cfg, _random, _random, **kw)
    b = evaluate(cfg, _random, _random, **kw)
    assert a == b
    d = json.loads(a.to_json())
    assert d["config"]["name"] == cfg.name and d["seed"] == 3 and d["rotations"] == 2
    assert d["reference_version"] == "icm_reference v1" and "default_rng" in d["seed_policy"]
    assert d["games"] == 16 and d["schema_version"] == 1


def test_evaluate_detects_a_clearly_better_agent():
    cfg = load_preset("6max_sng_wta")
    res = evaluate(cfg, _random, lambda rng: _Folder(), blocks=30, seed=1)
    assert res.ci.lo > 0 and res.roi_candidate > res.roi_baseline


class _Shover(Agent):
    def act(self, obs: Observation) -> Action:
        if obs.legal.max_raise_to is not None:
            return Action("raise", obs.legal.max_raise_to)
        return Action("call")


def test_duplicate_swap_cancels_identical_deterministic_agents():
    # Same deterministic agent on both sides: each swapped pair is the same game, so every block diff is 0.
    cfg = load_preset("6max_sng_wta")
    res = evaluate(cfg, lambda rng: _Shover(), lambda rng: _Shover(), blocks=3, seed=0)
    assert res.block_diffs == [0.0, 0.0, 0.0]


def test_evaluate_rejects_bad_arguments():
    cfg = load_preset("6max_sng_wta")
    with pytest.raises(ValueError):
        evaluate(cfg, _random, _random, blocks=1, seed=0)
    with pytest.raises(ValueError):
        evaluate(cfg, _random, _random, blocks=2, seed=0, rotations=7)


@pytest.mark.parametrize("players", [6, 9])
def test_each_rotation_adds_new_masks(players):
    for r in range(1, max_rotations(players) + 1):
        masks = _masks(players, r)
        assert len(masks) == 2 * r and len({tuple(m) for m in masks}) == 2 * r
        assert all(sum(m) in (players // 2, (players + 1) // 2) for m in masks)
    with pytest.raises(ValueError, match="rotations"):
        _masks(players, max_rotations(players) + 1)


def test_evaluate_rejects_rotations_that_repeat_masks():
    with pytest.raises(ValueError, match=r"1\.\.3"):
        evaluate(load_preset("6max_sng_wta"), _random, _random, blocks=2, seed=0, rotations=4)
