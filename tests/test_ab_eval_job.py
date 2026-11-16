"""#933 (ADR 0027 decision 4, F6c-1): the A/B evaluation job passes both launcher-trimmed results to tournament_ab."""
import base64
import json
import os
import shlex
import subprocess
import sys

import pytest

from stalker.tools import tournament_ab as T
from tests.test_icm_lambda_grid_jobs import ROOT, _run_stages_args
from tests.test_tournament_ab import PRESET

JOB = "jobs/e3-sng-bubble-ab-eval.yaml"


def _launcher():
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher
    return launcher


def _spec():
    return _launcher().parse_spec((ROOT / JOB).read_text(encoding="utf-8"), JOB)


def _stage():
    args = _run_stages_args(_spec().command)
    (stage,) = [args[i + 1] for i, a in enumerate(args) if a == "--stage"]
    return args, stage


def test_job_command_parses_with_the_real_tournament_ab_parser():
    args, stage = _stage()
    assert stage.startswith("ab=")
    a = T.build_parser().parse_args(shlex.split(stage.split("python3 -m stalker.tools.tournament_ab ", 1)[1]))
    assert (a.a, a.b) == ("$STALKER_RESUME", "$STALKER_RESUME_B")
    assert (a.presets, a.remaining, a.profiles, a.layouts, a.level_index) == (
        "9max_sng_503020", "4", "even,random,skewed", 3, "0")
    assert (a.games, a.sym_games, a.seed) == (400, 200, 10001)
    assert str(a.out) == args[args.index("--out") + 1] == _spec().result_path


def test_deadline_cost_and_comment():
    job = _spec()
    args, _ = _stage()
    assert float(args[args.index("--deadline-s") + 1]) <= job.max_minutes * 60 - 1800
    assert job.worst_case_usd == pytest.approx(0.96) and job.worst_case_usd <= 1.5
    text = (ROOT / JOB).read_text(encoding="utf-8")
    assert "= $0.96" in text and "43735226442" in text and "resume_run_b" in text
    assert "pip install -q -e '.[fast]'" in job.command


@pytest.mark.parametrize("a, b", [("", "x"), ("x", ""), ("", "")])
def test_job_fails_at_once_when_either_resume_is_empty(a, b, tmp_path):
    first = _spec().command.split("; mkdir -p /src", 1)[0]
    env = {k: v for k, v in os.environ.items() if k not in ("STALKER_RESUME", "STALKER_RESUME_B")}
    r = subprocess.run(["bash", "-c", first], env={**env, "STALKER_RESUME": a or "", "STALKER_RESUME_B": b or ""},
                       capture_output=True, text=True, encoding="utf-8", check=False)
    assert r.returncode == 3 and "resume_run_b" in r.stderr
    ok = {**env, "STALKER_RESUME": str(tmp_path), "STALKER_RESUME_B": str(tmp_path)}
    assert subprocess.run(["bash", "-c", first], env=ok, check=False).returncode == 0




def _pod_result(seed):
    """A small cash pod result as pod_train writes it (model + checkpoint) plus evaluation fields the launcher drops."""
    from stalker.e3 import tp_key as K
    from stalker.e3.mccfr import E3MCCFR
    from stalker.tools import pod_train as P
    from tests.test_pod_train_prior import cash_prior

    m = E3MCCFR.from_state(cash_prior())
    model = {"k": m.k, "n": m.n, "depth": m.depth, "iterations": m.iterations, "nodes": m.nodes, "menu": m.menu,
             "raise_cap": m.raise_cap, "avg_rule": m.avg_rule, "rng": m.rng.bit_generator.state, **m._grid(),
             "key_variant": m.key_variant, "stacks": m.stacks, "key_version": K.KEY_VERSIONS["c1"],
             "player_mix": list(m.player_mix), **m._count_state(), "ranges": m.ranges, "range_every": m.range_every,
             "snap_at": m.snap_at}
    return {"job": "x", "tier": "mid", "players": 4, "seed": seed, "iters": 1, "lbr": {"lbr_bb": 1.0}, "model": model,
            "checkpoint": {"format": "npz", "b64": base64.b64encode(P.pack(m)).decode()}}


@pytest.mark.slow
def test_launcher_trimmed_results_run_end_to_end_and_equal_policies_tie(tmp_path):
    L = _launcher()
    a_src, b_src = tmp_path / "a.json", tmp_path / "b.json"
    a_src.write_text(json.dumps(_pod_result(1)), encoding="utf-8")
    b_src.write_text(json.dumps(_pod_result(1)), encoding="utf-8")
    up_a, up_b = tmp_path / "resume.bin", tmp_path / "resume_b.bin"
    up_a.write_bytes(L.resume_payload(a_src, "111"))
    up_b.write_bytes(L.resume_payload(b_src, "222", which="resume_run_b"))
    out = tmp_path / "ab.json"
    assert T.main(["--a", str(up_a), "--b", str(up_b), "--presets", PRESET, "--remaining", "4", "--profiles", "even",
                   "--layouts", "1", "--games", "2", "--sym-games", "0", "--seed", "10001", "--out", str(out)]) == 0
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["primary"]["mean"] == 0.0 and res["verdict"] == "A" and res["adopted"] == "cold"
