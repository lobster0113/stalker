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


def test_compare_reports_two_models_and_decision_rule():
    out = R.compare(seeds=(0, 1, 2), exam_day=30)
    assert set(out) == {"exp", "power"}
    for m in out.values():
        assert m["adopt"] == (m["gain_mean"] > max(m["fixed"]["sd"], m["leitner"]["sd"]))
