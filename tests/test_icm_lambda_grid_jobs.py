"""#877: the lambda-grid baseline runs as two single-agent pod jobs, each with a deadline well before the pod limit."""
import shlex
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
JOBS = {"random": "random", "tag": "persona:tag"}


def _spec(name):
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    path = f"jobs/icm-lambda-grid-{name}.yaml"
    return launcher.parse_spec((ROOT / path).read_text(encoding="utf-8"), path)


def _run_stages_args(cmd):
    return shlex.split(cmd.split("python3 -m stalker.tools.run_stages ", 1)[1])


def test_old_combined_job_is_gone():
    assert not (ROOT / "jobs/icm-lambda-grid.yaml").exists(), "Delete it; use the per-agent jobs (#877)."


@pytest.mark.parametrize("name,agents", JOBS.items())
def test_job_runs_one_agent_with_deadline_before_the_pod_limit(name, agents):
    job = _spec(name)
    args = _run_stages_args(job.command)
    deadline = float(args[args.index("--deadline-s") + 1])
    assert job.max_minutes <= 120
    assert deadline <= job.max_minutes * 60 - 1800, "Lower --deadline-s to leave 30 min before max_minutes."
    assert job.hourly_usd * job.max_minutes / 60 <= 1.5
    stages = [args[i + 1] for i, a in enumerate(args) if a == "--stage"]
    names = [s.split("=", 1)[0] for s in stages]
    assert names == [name, "pair"]
    assert job.command.index("date -u +%s > /src/t0") < job.command.index("pip install"), "Record t0 before install."
    grid = stages[0].split(">&2; ", 1)
    assert "t0=$(cat /src/t0)" in grid[0] and "stage_start=" in grid[0], "Mark install time inside the measurement stage."
    grid = grid[1]
    assert f"--agents {agents} " in grid and "--lambda-grid" in grid and "--seed 0" in grid
    assert stages[1].endswith(f"{name}={'/src/' + name + '.json'}")
    assert job.result_path == f"/result/icm-lambda-grid-{name}.json"
    assert args[args.index("--out") + 1] == job.result_path
