"""#997 (ADR 0030 follow-up 3 prep): the lbr_icm distribution job runs tournament_eval --lbr-hands on a launcher-trimmed A result."""
import json
import os
import shlex
import subprocess

import pytest

from referee.e3 import tournament_eval as TE
from tests.test_ab_eval_job import _launcher, _pod_result
from tests.test_icm_lambda_grid_jobs import ROOT, _run_stages_args

JOB = "jobs/e3-sng-bubble-lbr-icm-eval.yaml"


def _spec():
    return _launcher().parse_spec((ROOT / JOB).read_text(encoding="utf-8"), JOB)


def _stage():
    args = _run_stages_args(_spec().command)
    (stage,) = [args[i + 1] for i, a in enumerate(args) if a == "--stage"]
    return args, stage


def _eval_args(stage):
    return shlex.split(stage.split("python3 -m referee.e3.tournament_eval ", 1)[1])


def test_command_parses_with_the_real_tournament_eval_parser():
    args, stage = _stage()
    assert stage.startswith("lbr=")
    ev = _eval_args(stage)
    assert ev[ev.index("--policy") + 1] == "$STALKER_RESUME"
    assert (ev[ev.index("--games") + 1], ev[ev.index("--seed") + 1], ev[ev.index("--lbr-hands") + 1]) == ("200", "10001", "2000")
    assert "--spots" not in ev   # spots v1: the 3 cells ADR 0030 describes
    assert ev[ev.index("--out") + 1] == args[args.index("--out") + 1] == _spec().result_path


def test_deadline_cost_and_comment():
    job = _spec()
    args, _ = _stage()
    assert float(args[args.index("--deadline-s") + 1]) <= job.max_minutes * 60 - 1800
    assert job.worst_case_usd == pytest.approx(0.48) and job.worst_case_usd <= 1.5   # cost cap, tests/test_cloud_launcher.py
    text = (ROOT / JOB).read_text(encoding="utf-8")
    assert "= $0.48" in text and "参考" not in text and "not CI" in text
    for run in ("43735226442", "43842144620", "43847129076"):
        assert run in text
    assert "pip install -q -e '.[fast]'" in job.command


@pytest.mark.parametrize("value", ["", None])
def test_job_fails_at_once_when_resume_is_empty(value, tmp_path):
    first = _spec().command.split("; mkdir -p /src", 1)[0]
    env = {k: v for k, v in os.environ.items() if k != "STALKER_RESUME"}
    if value is not None:
        env["STALKER_RESUME"] = value
    r = subprocess.run(["bash", "-c", first], env=env, capture_output=True, text=True, encoding="utf-8", check=False)
    assert r.returncode == 3 and "resume_run" in r.stderr
    assert subprocess.run(["bash", "-c", first], env={**env, "STALKER_RESUME": str(tmp_path)}, check=False).returncode == 0


@pytest.mark.slow
def test_launcher_trimmed_result_gives_lbr_pool_in_every_cell(tmp_path):
    src = tmp_path / "a.json"
    src.write_text(json.dumps(_pod_result(1)), encoding="utf-8")
    up = tmp_path / "resume.bin"
    up.write_bytes(_launcher().resume_payload(src, "111"))
    spots = tmp_path / "spots.json"
    spots.write_text(json.dumps({"spots": [TE.load_spots()[0]]}), encoding="utf-8")
    out = tmp_path / "eval.json"
    assert TE.main(["--policy", str(up), "--spots", str(spots), "--games", "2", "--seed", "10001",
                    "--lbr-hands", "2", "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["schema_version"] == TE.SCHEMA_VERSION_LBR == 2
    (cell,) = doc["cells"]
    assert cell["lbr_pool"]["hands"] == 2 and set(cell["lbr_pool"]) == {"mean", "se", "hands", "stage", "ante"}
