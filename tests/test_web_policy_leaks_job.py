"""#836: the pod job that writes the preflop leaks of the 120k c1 mid-6 web policy (screen + confirmation)."""
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
JOB = "jobs/web-policy-leaks-mid6-c1.yaml"
POLICY_URL = "https://raw.githubusercontent.com/lobster0113/stalker/ops/cloud/policies/42591543123/mid-6.json"


def _spec():
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    return launcher.parse_spec((ROOT / JOB).read_text(encoding="utf-8"), JOB)


def _flags(cmd, module):
    # the part of the job command that runs `python3 -m <module>`, up to the next `;`
    args = shlex.split(cmd.split(f"python3 -m {module} ", 1)[1].split("; ", 1)[0])
    flags, pos, i = {}, [], 0
    while i < len(args):
        if args[i].startswith("--"):
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                flags[args[i]] = args[i + 1]
                i += 2
                continue
            flags[args[i]] = True
        else:
            pos.append(args[i])
        i += 1
    return pos, flags


def _stages(cmd):
    args = shlex.split(cmd.split("python3 -m stalker.tools.run_stages ", 1)[1])
    return [args[i + 1] for i, a in enumerate(args) if a == "--stage"]


def test_job_probes_the_c1_policy_then_writes_the_leaks_file():
    job = _spec()
    cmd = job.command
    assert "refs/heads/main" in cmd and "pip install -q -e '.[fast]'" in cmd and POLICY_URL in cmd
    assert "python3 -m stalker.tools.run_stages --out /result/web-policy-leaks-mid6-c1.json" in cmd
    assert _flags(cmd, "stalker.tools.run_stages")[1]["--out"] == job.result_path
    stages = dict(v.split("=", 1) for v in _stages(cmd))
    assert list(stages) == ["probe", "confirm"]
    pos, probe = _flags(stages["probe"], "referee.e3.preflop_probe")
    assert pos == ["/src/mid-6.json"]
    assert probe["--deals"] == "300" and probe["--seed"] == "0" and probe["--workers"] == "32"
    _, leaks = _flags(stages["confirm"], "stalker.tools.policy_leaks")
    assert leaks["--workers"] == "32"          # one Pool after #854, so all 32 vCPUs (#855)
    assert leaks["--tier"] == "mid" and leaks["--policy"] == "/src/mid-6.json"
    assert leaks["--screen"] == probe["--json"]
    assert "--save-confirm" in leaks            # the confirmation stage runs on the pod
    assert leaks["--out"] == job.result_path == "/result/web-policy-leaks-mid6-c1.json"
    assert "42591543123/mid-6.json" in leaks["--evidence"]
    assert "--deals 300 --seed 0" in leaks["--command"]
    # the steps run in order: download, then the staged probe and leaks
    assert cmd.index(POLICY_URL) < cmd.index("run_stages") < cmd.index("referee.e3.preflop_probe") < cmd.index("stalker.tools.policy_leaks")


def test_job_stages_end_before_the_pod_limit():
    # #855: run_stages must hit its own deadline (and write stage-failure with timings) before the pod is cut off
    job = _spec()
    run = _flags(job.command, "stalker.tools.run_stages")[1]
    assert "--deadline-s" in run, "add --deadline-s to run_stages so a timeout still returns a result (#841)"
    deadline = float(run["--deadline-s"])
    assert 0 < deadline <= job.max_minutes * 60 - 600, f"--deadline-s {deadline} leaves < 600 s before the pod limit"


def test_job_worst_case_cost():
    job = _spec()
    assert job.vcpu == 32 and tuple(job.cpu_flavors) == ("cpu5c", "cpu3c")
    assert job.hourly_usd == 1.2 and job.max_minutes <= 150
    assert job.hourly_usd * job.max_minutes / 60 <= 3.0
