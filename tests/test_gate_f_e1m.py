import numpy as np
import pytest

from referee.gate_f import e1m as F
from referee.gate_s import e1m as S
from stalker.e1 import multiway_pushfold as M

STACKS = (10.0, 10.0, 10.0)


@pytest.fixture(scope="module")
def spec():
    return S.load()[0]


@pytest.fixture(scope="module")
def policy():
    return M.gate_f_policy("composite", "beginner", iters=300)


def test_follow_spec_reproduces_the_trained_bin_policy(policy, spec):
    sp = S.spot(STACKS, spec["payouts"])
    fs = policy(sp)
    assert set(fs) == set(S.DECISIONS)
    for d, f in fs.items():
        assert ((f.edges > 0) & (f.edges < 100)).all() and f.values.shape == (169,)
        assert len(f.bin_probs) == M.TIER_LEVELS["beginner"]
    # The bins are the trainer's quantile buckets.
    r = M.train(sp, "composite", "beginner", "icm", 300, nash_gains=np.zeros(3))
    tree = M.R._Tree(sp, M.R._value_fn(sp, "icm", 0, M.R.BASELINE_TOL, 300))
    k = M.TIER_LEVELS["beginner"]
    _, call_b = M._buckets(tree, r.strategy, 3, "composite", k)
    assert np.array_equal(fs["call", 2, 0].bins(fs["call", 2, 0].values), call_b[2, 0])


def test_zero_error_adds_no_loss(policy, spec):
    row = F.evaluate(policy, [STACKS], "beginner", sigma=0.0, spec=spec)["rows"][0]
    assert row["anchor_loss_added_pct"] == 0 and row["exploitability_added_pct"] == 0
    assert row["anchor_loss_noiseless_pct"] > 0      # the bottleneck itself costs something


def test_loss_grows_with_the_error(policy, spec):
    rows = [F.evaluate(policy, [STACKS], "beginner", sigma=s, spec=spec)["mean"] for s in (0.0, 6.0, 12.0, 20.0, 40.0)]
    for key in ("anchor_loss_pct", "exploitability_pct"):
        v = [r[key] for r in rows]
        assert all(b > a for a, b in zip(v, v[1:])), (key, v)


def test_the_anchor_has_no_anchor_loss(spec):
    sp, st = S.anchor(spec, STACKS)
    probs = {d: (st.push[d[1]] if d[0] == "push" else st.call[d[1], d[2]]) for d in S.DECISIONS}
    ex, al = F.losses(spec, STACKS, probs)
    assert al == pytest.approx(ex) and al < 0.01      # fictitious-play residual only


def test_result_is_report_only(policy, spec):
    r = F.evaluate(policy, [STACKS], "mid", spec=spec)
    assert r["verdict"].startswith("report_only") and r["sigma"] == 12.0 and r["env"] == "e1m"
