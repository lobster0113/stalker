"""#680: the job that continues seed 4 of the mixn c1 pod chain (run 41813684540) to 120,000 iterations."""
import math
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
    assert differ == {"--max-iters", "--workers", "--minutes", "--out"}
    assert int(long["--workers"]) < 16   # #491/#513: 16 workers may pass 64 GB at ~3M keys


def test_long_job_resumes_the_s4_result():
    from stalker.e3.mccfr import parse_mix
    from stalker.tools import pod_train as P
    f = _train_flags(_spec(LONG).command)
    assert P.job_name(f["--tier"], int(f["--players"]), f["--key-variant"], parse_mix(f["--player-mix"])) \
        == "e3-tp-mid-c1-mixn-pod"


SLOWEST_IT_S = 5.1    # 6.78 it/s (slowest host seen at 16 workers) x 0.75 for 12 workers
FAST_IT_S = 7.1      # 9.43 it/s (seed 4, run 41813684540) x 0.75
NON_TRAIN_MIN = 96   # run 41670499712: 159.82 min total - 73.8 min training = 86, plus 10 for the larger resume load


def _per_dispatch_iters(minutes, step, it_s):
    # train() checks the deadline only between steps, so it finishes the step that crosses it.
    step_min = step / it_s / 60
    return math.ceil(minutes / step_min) * step


def test_long_job_worst_case_cost():
    job = _spec(LONG)
    assert job.result_path == "/result/e3-tp-mid-c1-mixn-s4-long-pod32.json"
    assert job.vcpu == 32
    per = job.hourly_usd * job.max_minutes / 60
    assert per <= 4.0
    f = _train_flags(job.command)
    minutes, step = int(f["--minutes"]), int(f["--workers"]) * int(f["--batch"])
    # slowest host: deadline + one step overshoot + the longest observed non-training time must fit before the kill
    assert minutes + step / SLOWEST_IT_S / 60 + NON_TRAIN_MIN <= job.max_minutes
    for it_s in (FAST_IT_S, SLOWEST_IT_S):
        dispatches = math.ceil((int(f["--max-iters"]) - 40000) / _per_dispatch_iters(minutes, step, it_s))
        assert dispatches <= 3, it_s   # header comment: 3 dispatches
        assert dispatches * per <= 12.0


def test_per_dispatch_iters_counts_the_step_that_crosses_the_deadline():
    assert _per_dispatch_iters(80, 6000, 5.1) == 30000   # 4 steps end at 78.4 min < 80, so a 5th runs
    assert _per_dispatch_iters(75, 6000, 5.1) == 24000
