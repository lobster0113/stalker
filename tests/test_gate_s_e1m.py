import json
import subprocess
import sys

import numpy as np
import pytest

from referee.gate_s import SpotError
from referee.gate_s import e1m as S


@pytest.fixture(scope="module")
def spec():
    return S.load()[0]


def test_spot_set_loads_with_hash_and_enough_golden_spots():
    spec, sha = S.load()
    assert len(sha) == 64 and len(spec["golden"]) >= 5 and len(spec["base"]) == 8
    assert {tuple(g["decision"])[0] for g in spec["golden"]} == {"push", "call"}


def test_one_seat_moves_inside_its_bucket_and_draws_are_seeded(spec):
    ps = S.pairs(spec)
    assert ps == S.pairs(spec) and len(ps) == spec["per_base"] * len(spec["base"])
    edges = spec["bucket_edges"]
    for a, b in ps:
        moved = [i for i in range(3) if a[i] != b[i]]
        assert len(moved) == 1 and S.bucket(a[moved[0]], edges) == S.bucket(b[moved[0]], edges)
        # every pairwise effective stack stays in its bucket too
        assert all(S.bucket(min(a[i], a[j]), edges) == S.bucket(min(b[i], b[j]), edges)
                   for i in range(3) for j in range(i + 1, 3))


def test_bad_spot_files_are_rejected(tmp_path, spec):
    few = tmp_path / "few.json"
    few.write_text(json.dumps({**spec, "golden": spec["golden"][:4]}), encoding="utf-8")
    with pytest.raises(SpotError, match="at least 5"):
        S.load(few)
    g = spec["golden"][0]
    cross = tmp_path / "cross.json"
    far = 25.0 if g["base"][g["seat"]] <= 15 else 3.0
    cross.write_text(json.dumps({**spec, "golden": [{**g, "to": far}] + spec["golden"][1:]}), encoding="utf-8")
    with pytest.raises(SpotError, match="crosses a bucket edge"):
        S.load(cross)


@pytest.mark.slow
def test_the_anchor_passes(spec):
    r = S.evaluate(S.nash_policy_for(spec), spec)
    assert r["passed"], r["fails"]
    assert r["decisions"] > 0 and set(r["tv_p95_by_kind"]) == {"push", "call"}


@pytest.mark.slow
def test_a_policy_that_reads_the_raw_stacks_fails_on_tv(spec):
    r = S.evaluate(S.oversensitive_policy_for(spec), spec)
    assert not r["passed"] and any(f.startswith("tv p95") for f in r["fails"])


@pytest.mark.slow
def test_a_flattened_policy_fails_on_the_golden_spots(spec):
    r = S.evaluate(S.flat_policy_for(spec), spec)
    assert r["tv_p95"] == 0.0 and not any(g["ok"] for g in r["golden"])
    assert any("too flat" in f for f in r["fails"])


@pytest.mark.slow
def test_tp_change_is_measured_in_scale_steps(spec):
    nash = S.nash_policy_for(spec)

    def jumpy(sp):   # the TP value moves with every BB of any stack
        return {d: (p, np.full(169, sum(sp.stacks) // S.BB)) for d, (p, _) in nash(sp).items()}

    r = S.evaluate(jumpy, spec)
    assert r["tp_change_p95"] >= 1 and any(f.startswith("tp change") for f in r["fails"])


def test_loss_is_zero_for_the_anchors_best_action(spec):
    a = tuple(float(x) for x in spec["base"][0])
    for d in S.DECISIONS:
        adv, w, _ = S._dec(spec, a, d)
        if w is not None:
            assert S.loss_pct(spec, a, d, (adv > 0).astype(float)) == pytest.approx(0.0, abs=1e-12)
            assert S.loss_pct(spec, a, d, (adv <= 0).astype(float)) > 0


@pytest.mark.slow
def test_cli_check_exits_zero(tmp_path):
    out = tmp_path / "s.json"
    p = subprocess.run([sys.executable, "-m", "referee.gate_s", "--env", "e1m", "--check", "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stderr
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["env"] == "e1m" and len(res["sha256"]) == 64 and set(res["policies"]) == {"nash_anchor", "oversensitive", "flat"}
