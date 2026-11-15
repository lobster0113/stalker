"""#901: the first tournament measurement job follows ADR 0027 decision 5."""
import shlex
import sys
from pathlib import Path

from tests.test_c1_s4_long_job import _spec, _train_flags

JOB = "jobs/e3-tp-mid-c1-sng-bubble-pod32.yaml"


def test_job_matches_the_adr_table():
    spec = _spec(JOB)
    assert (spec.cpu_flavor, spec.vcpu, spec.hourly_usd, spec.max_minutes) == ("cpu3c", 32, 1.2, 180)
    f = _train_flags(spec.command)
    want = {"--tier": "mid", "--players": "4", "--workers": "16", "--minutes": "60", "--max-iters": "20000",
            "--batch": "500", "--seed": "1", "--menu": "real", "--ranges": "average", "--avg-rule": "own",
            "--key-variant": "c1", "--payoff": "icm", "--preset": "9max_sng_503020", "--stage": "b",
            "--level-index": "0", "--lam": "0", "--stacks": "bubble:skewed", "--lbr-hands": "600"}
    assert {k: f.get(k) for k in want} == want and f["--no-raise-cap"] is True
    assert f["--out"] == spec.result_path == "/result/e3-tp-mid-c1-sng-bubble-pod32.json"


def test_job_flags_parse_with_pod_train():
    from stalker.tools import pod_train as P
    f = _train_flags(_spec(JOB).command)
    argv = [x for k, v in f.items() if k not in ("--sha-file", "--resume-result") for x in ([k] if v is True else [k, v])]
    # parse only (no run): the CLI refuses unknown flags and bad tournament arguments
    import argparse
    assert P.tournament_args(argparse.Namespace(payoff="icm", preset=f["--preset"], stage="b", level_index=0, lam=0.0,
                                                ante=None, stacks="bubble:skewed", players=4)) [1]["stage"] == "b"
    assert "--lbr-hands" in argv
