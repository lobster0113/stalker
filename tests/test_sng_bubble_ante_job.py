"""#996: the SNG bubble (stage b) training job with the BB ante, ADR 0027 decision 2 step 3."""
import json

import pytest

from tests.test_c1_s4_long_job import _spec, _train_flags
from tests.test_cloud_launcher import L, ROOT
from tests.test_sng_bubble_job import _argv, _parse

BUBBLE = "jobs/e3-tp-mid-c1-sng-bubble-pod32.yaml"
JOB = "jobs/e3-tp-mid-c1-sng-bubble-ante-pod32.yaml"
NAME = "e3-tp-mid-c1-sng-bubble-ante-pod32"


def test_differs_from_the_bubble_job_only_by_ante_and_name():
    spec, bubble = _spec(JOB), _spec(BUBBLE)
    f, b = _train_flags(spec.command), _train_flags(bubble.command)
    assert f.pop("--ante") == "100" and "--ante" not in b
    assert f.pop("--out") == spec.result_path == f"/result/{NAME}.json"
    b.pop("--out")
    assert f == b
    assert (f["--stage"], f["--players"], f["--lam"], f["--stacks"], f["--seed"], f["--lbr-hands"]) == (
        "b", "4", "0", "bubble:skewed", "1", "600")
    assert "--prior-result" not in f
    assert spec.name == NAME
    mine = spec.command.replace(NAME, "X").replace(" --ante 100", "")
    assert mine == bubble.command.replace("e3-tp-mid-c1-sng-bubble-pod32", "X"), "pod command must stay the bubble job's"


def test_flags_parse_with_pod_train():
    a = _parse(_argv(_train_flags(_spec(JOB).command)))
    assert (a.ante, a.stage, a.payoff, a.preset) == (100, "b", "icm", "9max_sng_503020")


def test_worst_case_cost_and_iteration_budget():
    job = L.load_spec(ROOT / JOB)
    assert job.hourly_usd * job.max_minutes / 60 <= 3.60
    (_, _, median), = job.flavors
    assert median > 0
    f = _train_flags(_spec(JOB).command)
    # median 12 it/s comes from the bubble job's F6b normal-host runs (11.36-11.84; see its yaml comment)
    assert int(f["--max-iters"]) / median <= int(f["--minutes"]) * 60


@pytest.mark.slow
def test_small_run_uses_the_tb1_slot(tmp_path):
    from stalker.tools import pod_train as P
    from tests.test_sng_mid_jobs import _small_argv

    out = tmp_path / "r.json"
    assert P.main(_small_argv(_train_flags(_spec(JOB).command), out)) == 0
    r = json.loads(out.read_text(encoding="utf-8"))
    model = r["model"]
    assert (model["ante"], model["stage"], model["train_env"]["stage"]) == (100, "b", "b")
    policy = next(p for p in P.unpack(out, tmp_path / "u") if p.name.endswith(".policy.json"))
    keys = [k for k in json.loads(policy.read_text(encoding="utf-8"))["average"] if not k.startswith("call|")]
    assert keys and {k.split("|")[8] for k in keys} == {"tb1"}
