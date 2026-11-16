"""#935: the F7a-cell lambda-grid baselines run the policy job's exact grid with only the agent swapped."""
import shlex

import pytest

from stalker.tools import icm_grid
from tests.test_icm_lambda_grid_jobs import ROOT, _run_stages_args

POLICY = "e3-sng-bubble-lambda-policy"
JOBS = {"random": "random", "tag": "persona:tag"}


def _spec(name):
    import sys
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    path = f"jobs/{name}.yaml"
    return launcher.parse_spec((ROOT / path).read_text(encoding="utf-8"), path)


def _stages(job):
    args = _run_stages_args(job.command)
    return args, [args[i + 1] for i, a in enumerate(args) if a == "--stage"]


def _grid_call(stage, monkeypatch, tmp_path):
    """Feed the stage's icm_grid argv to the real CLI parser and capture what run_grid would get."""
    argv = shlex.split(stage.split(">&2; ", 1)[1].split("python3 -m stalker.tools.icm_grid ", 1)[1])
    out = argv.index("--out")
    argv[out + 1] = str(tmp_path / "grid.json")
    seen = {}

    def fake(*a):
        seen["args"] = a
        return {}

    monkeypatch.setattr(icm_grid, "run_grid", fake)
    assert icm_grid.main(argv) == 0
    return seen["args"]


@pytest.mark.parametrize("name,agents", JOBS.items())
def test_grid_equals_the_policy_job_but_for_agents(name, agents, monkeypatch, tmp_path):
    _, (policy_stage, _) = _stages(_spec(POLICY))
    job = _spec(f"icm-lambda-grid-{name}-f7")
    args, stages = _stages(job)
    assert [s.split("=", 1)[0] for s in stages] == [name, "pair"]
    got = list(_grid_call(stages[0], monkeypatch, tmp_path))
    want = list(_grid_call(policy_stage, monkeypatch, tmp_path))
    assert want[5] == "policy:$STALKER_RESUME" and got[5] == agents
    got[5] = want[5]
    assert got == want, "Keep the icm_grid flags identical to the F7a policy job; only --agents may differ."
    assert got[4] == 10001 and got[0] == ["9max_sng_503020"] and got[1] == [4]


@pytest.mark.parametrize("name", JOBS)
def test_cost_deadline_and_result_path(name):
    job = _spec(f"icm-lambda-grid-{name}-f7")
    args, stages = _stages(job)
    deadline = float(args[args.index("--deadline-s") + 1])
    assert deadline <= job.max_minutes * 60 - 1800, "Lower --deadline-s to leave 30 min before max_minutes."
    assert job.worst_case_usd <= 0.50, "Worst case must stay at or below $0.50 (#935)."
    assert job.command.index("date -u +%s > /src/t0") < job.command.index("pip install"), "Record t0 before install."
    assert "t0=$(cat /src/t0)" in stages[0] and "stage_start=" in stages[0]
    assert stages[1].endswith(f"{name}=/src/{name}.json")
    assert args[args.index("--out") + 1] == job.result_path == f"/result/icm-lambda-grid-{name}-f7.json"
