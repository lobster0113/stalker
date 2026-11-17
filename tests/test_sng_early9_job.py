"""#943: the 9-max SNG early-stage c1 measurement job (ADR 0027 F10) and a small local run of its arguments."""
import json

import pytest

from tests.test_c1_s4_long_job import _spec, _train_flags
from tests.test_sng_bubble_job import _argv, _parse

JOB = "jobs/e3-tp-mid-c1-sng-early9-pod32.yaml"


def test_job_flags_parse_with_pod_train():
    spec = _spec(JOB)
    f = _train_flags(spec.command)
    a = _parse(_argv(f))
    assert (a.players, a.stage, a.key_variant, a.payoff, a.max_iters) == (9, "e", "c1", "icm", 80000)
    assert (a.preset, a.level_index, a.lam, a.stacks, a.menu, a.ranges, a.avg_rule, a.no_raise_cap) == (
        "9max_sng_503020", 0, 0.0, "bubble:even", "real", "average", "own", True)
    assert f["--out"] == spec.result_path == "/result/e3-tp-mid-c1-sng-early9-pod32.json"


def test_worst_case_cost_is_at_most_4_usd():
    spec = _spec(JOB)
    assert spec.hourly_usd * spec.max_minutes / 60 <= 4.00


def test_median_it_s_declared_and_minutes_end_training_first():
    spec = _spec(JOB)
    assert list(spec.median_iters_per_s) == [18]
    f = _train_flags(spec.command)
    assert int(f["--max-iters"]) / spec.median_iters_per_s[0] >= int(f["--minutes"]) * 60, "raise --max-iters"


def _small_argv(f, players, out):
    # the job's own flags, shrunk to a few iterations on one worker
    small = {**f, "--players": str(players), "--workers": "1", "--max-iters": "4", "--batch": "2", "--minutes": "5",
             "--lbr-hands": "4", "--out": str(out)}
    for k in ("--sha-file", "--resume-result"):
        small.pop(k, None)
    return _argv(small)


@pytest.mark.slow
@pytest.mark.parametrize("players", [9, 7, 8])
def test_small_run_writes_a_te0_result_without_ep_positions(players, tmp_path):
    from stalker.tools import pod_train as P

    out = tmp_path / "r.json"
    assert P.main(_small_argv(_train_flags(_spec(JOB).command), players, out)) == 0
    r = json.loads(out.read_text(encoding="utf-8"))
    assert (r["players"], r["iters"], r["train_env"]["stage"]) == (players, 4, "e")
    policy = next(p for p in P.unpack(out, tmp_path / "u") if p.name.endswith(".policy.json"))
    keys = [k for k in json.loads(policy.read_text(encoding="utf-8"))["average"] if not k.startswith("call|")]
    assert keys, "the small run learned no keys"
    assert not [k for k in keys if k.startswith("EP")], "c1 keys must use the 7-9 player names of #940, not EP<n>"
    assert {k.split("|")[1] for k in keys} == {f"n{players}"}
    assert {k.split("|")[8] for k in keys} == {"te0"}, "every key must carry the early-stage slot te0"
