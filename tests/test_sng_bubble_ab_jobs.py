"""#926 (ADR 0027 decision 4, F6b): the warm-start A/B training jobs run the same command as arm A seed 1 (#901)."""
import base64
import json
import os
import subprocess

import pytest

from tests.test_c1_s4_long_job import ROOT, _spec, _train_flags

A1 = "jobs/e3-tp-mid-c1-sng-bubble-pod32.yaml"
ARM_A = {s: f"jobs/e3-tp-mid-c1-sng-bubble-s{s}-pod32.yaml" for s in (2, 3)}
ARM_B = {s: f"jobs/e3-tp-mid-c1-sng-bubble-prior-s{s}-pod32.yaml" for s in (1, 2, 3)}
PRIOR_RUN = "41813684540"
RESUME = '${STALKER_RESUME:+--resume-result "$STALKER_RESUME"}'
GUARD = ('test -n "$STALKER_RESUME" || { echo "STALKER_RESUME empty - dispatch with resume_run=41813684540 '
         '(the warm-start prior)" >&2; exit 3; }; ')


def _name(rel):
    return rel.rsplit("/", 1)[1].removesuffix(".yaml")


def _expected_command(rel, seed, prior):
    """Arm A seed 1's command with only the seed, the output name and (arm B) the resume flag swapped."""
    cmd = _spec(A1).command.replace("--seed 1 ", f"--seed {seed} ")
    cmd = cmd.replace("/result/e3-tp-mid-c1-sng-bubble-pod32.json", f"/result/{_name(rel)}.json")
    if prior:
        cmd = cmd.replace(RESUME, '--prior-result "$STALKER_RESUME"').replace("set -e; ", "set -e; " + GUARD, 1)
    return cmd


@pytest.mark.parametrize("rel, seed, prior", [*((r, s, False) for s, r in ARM_A.items()),
                                              *((r, s, True) for s, r in ARM_B.items())])
def test_arm_jobs_are_arm_a_seed_1_but_for_seed_output_and_prior(rel, seed, prior):
    base, job = _spec(A1), _spec(rel)
    assert job.name == _name(rel)
    assert job.command == _expected_command(rel, seed, prior), "Keep the A/B arms on the same command (ADR 0027 d4)."
    same = ("image", "cpu_flavor", "vcpu", "disk_gb", "max_minutes", "hourly_usd")
    assert {k: getattr(job, k) for k in same} == {k: getattr(base, k) for k in same}
    assert job.result_path == f"/result/{job.name}.json"
    f, f1 = _train_flags(job.command), _train_flags(base.command)
    differ = {k for k in f.keys() | f1.keys() if f.get(k) != f1.get(k)}
    want = {"--seed", "--out"} | ({"--prior-result", "--resume-result"} if prior else set())
    assert differ == (want - {"--seed"} if seed == 1 else want)
    assert f["--seed"] == str(seed)
    if prior:
        assert f["--prior-result"] == "$STALKER_RESUME" and "--resume-result" not in f
    # same compute: the iteration and clock limits, workers and evaluation size are arm A's
    assert (f["--max-iters"], f["--minutes"], f["--workers"], f["--lbr-hands"]) == ("20000", "60", "16", "600")


def test_seeds_cover_one_to_three_per_arm():
    assert _train_flags(_spec(A1).command)["--seed"] == "1"
    assert sorted(_train_flags(_spec(r).command)["--seed"] for r in ARM_A.values()) == ["2", "3"]
    assert sorted(_train_flags(_spec(r).command)["--seed"] for r in ARM_B.values()) == ["1", "2", "3"]


@pytest.mark.parametrize("rel", [*ARM_A.values(), *ARM_B.values()])
def test_worst_case_cost_is_in_the_comment_and_under_the_training_cap(rel):
    job = _spec(rel)
    worst = job.hourly_usd * job.max_minutes / 60
    assert worst == pytest.approx(3.6) and job.worst_case_usd == pytest.approx(worst)
    assert f"= ${worst:.2f}" in (ROOT / rel).read_text(encoding="utf-8")
    cap = json.loads((ROOT / "harness" / "budget.json").read_text(encoding="utf-8"))["monthly_cap_usd"]
    assert job.worst_case_usd <= 0.1 * cap


@pytest.mark.parametrize("rel", ARM_B.values())
def test_arm_b_fails_at_once_without_the_prior_upload(rel, tmp_path):
    first = _spec(rel).command.split(" python3 -c", 1)[0]
    env = {k: v for k, v in os.environ.items() if k != "STALKER_RESUME"}
    r = subprocess.run(["bash", "-c", first], env={**env, "STALKER_RESUME": ""}, capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 3 and f"resume_run={PRIOR_RUN}" in r.stderr
    assert subprocess.run(["bash", "-c", first], env={**env, "STALKER_RESUME": str(tmp_path)}).returncode == 0


@pytest.mark.parametrize("rel", ARM_B.values())
def test_arm_b_comment_names_the_prior_run_its_size_and_expiry(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert f"resume_run={PRIOR_RUN}" in text and "RESUME_MAX_BYTES" in text and "expires ~12-04" in text
    assert "42591543123" in text   # why not the 120k run: over the upload cap


def test_a_launcher_trimmed_cash_pod_result_seeds_the_arm_b_table(tmp_path):
    """The prior reaches the pod as launcher.resume_payload output; pod_train must still find model + checkpoint."""
    import sys
    sys.path.insert(0, str(ROOT / "harness/cloud"))
    import launcher as L

    from stalker.e3 import tp_key as K
    from stalker.e3.mccfr import E3MCCFR
    from stalker.tools import pod_train as P
    from tests.test_pod_train_prior import cash_prior

    st = cash_prior()
    m = E3MCCFR.from_state(st)
    model = {"k": m.k, "n": m.n, "depth": m.depth, "menu": m.menu, "raise_cap": m.raise_cap, "avg_rule": "own",
             "key_variant": "c1", "stacks": "sampled", "key_version": K.KEY_VERSIONS["c1"], "ranges": "average",
             "player_mix": list(m.player_mix), **m._count_state()}
    # a cash mixn result as the 40k run wrote it: evaluation fields beside the model (the launcher drops them)
    res = {"job": "e3-tp-mid-c1-mixn-pod", "tier": "mid", "players": 6, "seed": 4, "iters": 40000,
           "lbr": {"lbr_bb": 2.44}, "by_players": {"4": {}}, "model": model,
           "checkpoint": {"format": "npz", "b64": base64.b64encode(P.pack(m)).decode()}}
    src = tmp_path / "result.json"
    src.write_text(json.dumps(res), encoding="utf-8")
    up = tmp_path / "resume.bin"
    up.write_bytes(L.resume_payload(src, PRIOR_RUN))

    f = _train_flags(_spec(ARM_B[1]).command)
    env, _ = P.tournament_env(f["--preset"], int(f["--players"]), f["--stage"], int(f["--level-index"]),
                              float(f["--lam"]), f["--stacks"])
    arm_b = E3MCCFR(int(f["--seed"]), K.TIER_K[f["--tier"]], int(f["--players"]), K.TIER_DEPTH[f["--tier"]],
                    f["--menu"], None, f["--ranges"], avg_rule=f["--avg-rule"], key_variant=f["--key-variant"],
                    stacks=f["--stacks"], **env)
    got, rec = P.read_prior(up)
    assert rec["run_id"] == PRIOR_RUN
    assert P.apply_prior(arm_b, got) == 3
    assert all("|tb0|" in k for k in arm_b.policy() if "|" in k and k.count("|") > 3)
