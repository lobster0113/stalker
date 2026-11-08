"""#680: the job that continues seed 4 of the mixn c1 pod chain (run 41813684540) to 120,000 iterations."""
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
LONG = "jobs/e3-tp-mid-c1-mixn-s4-long-pod32.yaml"
BASE = "jobs/e3-tp-mid-c1-mixn-s4-pod32.yaml"


def _spec(rel):
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    return launcher.parse_spec((ROOT / rel).read_text(encoding="utf-8"), rel)


def _train_flags(cmd):
    tail = cmd.split("python3 -m stalker.tools.pod_train", 1)[1]
    args = shlex.split(re.sub(r"\$\{STALKER_RESUME:\+[^}]*\}", "--resume-result R", tail))
    flags, i = {}, 0
    while i < len(args):
        if i + 1 < len(args) and not args[i + 1].startswith("--"):
            flags[args[i]] = args[i + 1]
            i += 2
        else:
            flags[args[i]] = True
            i += 1
    return flags


def test_long_job_keeps_the_s4_training_flags():
    long, base = _train_flags(_spec(LONG).command), _train_flags(_spec(BASE).command)
    assert long["--seed"] == "4" and long["--max-iters"] == "120000" and long["--key-variant"] == "c1"
    assert long["--player-mix"] == "2,3,4,5,6" and long["--resume-result"] == "R"
    assert long["--out"] == "/result/e3-tp-mid-c1-mixn-s4-long-pod32.json"
    # everything that decides the table and the resume check stays as in the s4 job (workers only change speed/memory)
    differ = {k for k in long.keys() | base.keys() if long.get(k) != base.get(k)}
    assert differ == {"--max-iters", "--workers", "--out"}
    assert int(long["--workers"]) < 16   # #491/#513: 16 workers may pass 64 GB at ~3M keys


def test_long_job_resumes_the_s4_result():
    from stalker.e3.mccfr import parse_mix
    from stalker.tools import pod_train as P
    f = _train_flags(_spec(LONG).command)
    assert P.job_name(f["--tier"], int(f["--players"]), f["--key-variant"], parse_mix(f["--player-mix"])) \
        == "e3-tp-mid-c1-mixn-pod"


def test_long_job_worst_case_cost():
    job = _spec(LONG)
    assert job.result_path == "/result/e3-tp-mid-c1-mixn-s4-long-pod32.json"
    assert job.vcpu == 32
    per = job.hourly_usd * job.max_minutes / 60
    assert per <= 4.0
    assert 3 * per <= 12.0   # expected dispatches 40k -> 120k (header comment)
    assert job.max_minutes >= 90 + 60   # training ceiling plus pip, resume load and evaluation
