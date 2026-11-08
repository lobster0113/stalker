import pytest

from stalker.service import review_sched as R


def test_both_schedulers_share_next_due_interface():
    assert R.next_due_fixed(0, 1) == (1, 3)
    assert R.next_due_fixed(1, 0) == (2, 7)  # grade ignored
    assert R.next_due_fixed(2, 1) == (3, None)
    assert R.next_due_leitner(0, 1) == (1, 2)
    assert R.next_due_leitner(3, 0) == (0, 1)  # forgot -> box 0
    assert R.next_due_leitner(5, 1) == (5, 32)  # capped


def test_unknown_model_message():
    with pytest.raises(ValueError, match="exp"):
        R.recall_prob("nope", 1.0, 1.0)


def test_simulation_is_seeded_and_common_random_numbers():
    a = R.simulate("leitner", R.Learner("exp"), 3, exam_day=20)
    assert a == R.simulate("leitner", R.Learner("exp"), 3, exam_day=20)
    assert a != R.simulate("leitner", R.Learner("exp"), 4, exam_day=20)


def test_fixed_reviews_exactly_three_times_and_long_arm_keeps_going():
    _, fixed = R.simulate_run("fixed", R.Learner("exp"), 1, exam_day=60)
    assert fixed == 3.0  # 30 items x 3 reviews; budget 4/day is enough
    _, long = R.simulate_run("fixed_long", R.Learner("exp"), 1, exam_day=60)
    assert long > fixed


def test_reviewing_beats_not_reviewing_and_power_path_runs():
    for model in ("exp", "power"):
        learner = R.Learner(model)
        reviewed = R.simulate("leitner", learner, 2, exam_day=30)
        untouched = float(R.recall_prob(model, 30, 2.0))  # typical item strength, never reviewed
        assert reviewed > untouched


def test_aggregate_uses_paired_gain_and_rule():
    rows = [R.seed_rows(sd, exam_days=(60,)) for sd in (0, 1, 2)]
    agg = R.aggregate(rows)
    assert len(agg) == 2 * 3  # models x schedulers at one exam day
    for r in agg:
        if r["scheduler"] == "fixed":
            assert "adopt" not in r
        else:
            fixed_sd = next(x["score_sd"] for x in agg if x["model"] == r["model"] and x["scheduler"] == "fixed")
            assert r["adopt"] == (r["gain_vs_fixed_mean"] > max(r["score_sd"], fixed_sd))
    assert any(r["reviews_per_item"] > 3 for r in agg if r["scheduler"] == "leitner")
