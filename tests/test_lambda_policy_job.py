"""#916: the lambda-selection job plays the F5 policy handed over by resume_run, under a deadline before the pod limit."""
import os
import shlex
import subprocess

from tests.test_icm_lambda_grid_jobs import ROOT, _run_stages_args

JOB = "jobs/e3-sng-bubble-lambda-policy.yaml"


def _spec():
    import sys
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    return launcher.parse_spec((ROOT / JOB).read_text(encoding="utf-8"), JOB)


def _grid_flags(stage):
    args = shlex.split(stage.split(">&2; ", 1)[1].split("python3 -m stalker.tools.icm_grid ", 1)[1])
    flags, i = {}, 0
    while i < len(args):
        if i + 1 < len(args) and not args[i + 1].startswith("--"):
            flags[args[i]], i = args[i + 1], i + 2
        else:
            flags[args[i]], i = True, i + 1
    return flags


def test_job_grid_flags_deadline_and_cost():
    job = _spec()
    args = _run_stages_args(job.command)
    deadline = float(args[args.index("--deadline-s") + 1])
    assert deadline <= job.max_minutes * 60 - 1800, "Lower --deadline-s to leave 30 min before max_minutes."
    assert job.hourly_usd * job.max_minutes / 60 <= 3.0
    stages = [args[i + 1] for i, a in enumerate(args) if a == "--stage"]
    assert [s.split("=", 1)[0] for s in stages] == ["policy", "pair"]
    f = _grid_flags(stages[0])
    want = {"--presets": "9max_sng_503020", "--remaining": "4", "--profiles": "even,random,skewed", "--layouts": "3",
            "--level-index": "0", "--games": "1000", "--seed": "10001", "--agents": "policy:$STALKER_RESUME",
            "--lambda-grid": True, "--out": "/src/policy.json"}
    assert f == want
    assert stages[1].endswith("policy=/src/policy.json")
    assert args[args.index("--out") + 1] == job.result_path == "/result/e3-sng-bubble-lambda-policy.json"
    assert "pip install -q -e '.[fast]'" in job.command, "Install numba: policy seats are ~6x slower without it."


def test_job_fails_at_once_without_a_resume_upload(tmp_path):
    first = _spec().command.split("; mkdir -p /src", 1)[0]
    env = {k: v for k, v in os.environ.items() if k != "STALKER_RESUME"}
    r = subprocess.run(["bash", "-c", first], env={**env, "STALKER_RESUME": ""}, capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 3 and "resume_run=43735226442" in r.stderr
    r = subprocess.run(["bash", "-c", first], env={**env, "STALKER_RESUME": str(tmp_path)}, capture_output=True)
    assert r.returncode == 0
