import dataclasses

import pytest

torch = pytest.importorskip("torch")
from referee import gate_l  # noqa: E402
from referee.gate_l import Report, check_l6, run_gate_l  # noqa: E402
from referee.metrics import gate_l as gate_l_metrics  # noqa: E402
from stalker.rl.train import TrainConfig, Trainer  # noqa: E402


def test_l6_passes_for_a_two_game_batch():
    r = Report()
    check_l6(r)
    assert r.ok, r.failures
    assert r.counts["L6"] == [2, 2]


def test_l6_fails_for_a_game_mixed_segment():
    tr = Trainer(gate_l._l6_config(), TrainConfig(seed=6, games_per_iter=1, epochs=1, minibatch_segments=6))
    a, b = tr.play_game("g-a"), tr.play_game("g-b")
    bad = dataclasses.replace(a[0], observations=a[0].observations + b[0].observations[:1])
    r = Report()
    check_l6(r, segments=[bad] + a[1:] + b, trainer=tr)
    assert not r.ok and "game_id" in r.failures[0]


def test_l6_fails_for_a_segment_that_did_not_start_from_zero_state():
    tr = Trainer(gate_l._l6_config(), TrainConfig(seed=6, games_per_iter=1, epochs=1, minibatch_segments=6))
    segs = tr.play_game("g-a") + tr.play_game("g-b")
    segs[0] = dataclasses.replace(segs[0], initial_state_zero=False)
    r = Report()
    check_l6(r, segments=segs, trainer=tr)
    assert not r.ok and "zero GRU state" in r.failures[0]


def test_full_gate_l_covers_l2_and_l6_with_the_rl_agent():
    """CI rl job path: L2 and L6 appear in gate_l_items, nothing is skipped for lack of torch."""
    report = run_gate_l()
    assert report.ok, report.failures
    assert not any("torch" in s for s in report.skipped)
    items = gate_l_metrics(report)["gate_l_items"]
    assert items["L2"] == [1, 1] and items["L6"][1] >= 2 and items["L6"][0] == items["L6"][1]
    assert items["L1"][1] == 6 and items["L5"][1] == 6  # 3 agents (random, reference, rl_policy_v0) x 2 presets / 2 checks
