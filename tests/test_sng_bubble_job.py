"""#901: the first tournament measurement job follows ADR 0027 decision 5."""
from pathlib import Path

import pytest

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


def _argv(f):
    return [x for k, v in f.items() for x in ([k] if v is True else [k, v])]


def _parse(argv):
    from stalker.tools import pod_train as P
    return P.build_parser().parse_args(argv)


def test_job_flags_parse_with_pod_train():
    f = _train_flags(_spec(JOB).command)
    a = _parse(_argv(f))
    assert (a.payoff, a.preset, a.stage, a.lam, a.stacks, a.lbr_hands) == (
        "icm", "9max_sng_503020", "b", 0.0, "bubble:skewed", 600)


def test_unknown_job_flag_fails_to_parse(capsys):
    import pytest
    with pytest.raises(SystemExit):
        _parse(_argv(_train_flags(_spec(JOB).command)) + ["--bogus"])
    assert "--bogus" in capsys.readouterr().err


@pytest.mark.parametrize("job", sorted(p.name for p in (Path(__file__).resolve().parent.parent / "jobs").glob("e3-*-pod32.yaml")))
def test_every_pod_train_job_parses(job):
    command = _spec("jobs/" + job).command
    if "stalker.tools.pod_train" not in command:
        pytest.skip("not a pod_train job")
    _parse(_argv(_train_flags(command)))
