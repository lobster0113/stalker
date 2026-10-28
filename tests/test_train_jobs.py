import json

import pytest
import yaml

from stalker import train_jobs as T
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_run_and_summarize_e2_mccfr(tmp_path, monkeypatch):
    import referee.e2.lbr as lbr

    monkeypatch.setattr(lbr, "exploitability_lb", lambda pol, hands, seed, abstraction: {"lbr_bb": 1.0, "stderr_bb": 0.1, "hands": hands})
    for seed in (1, 2):
        T.run("e2-mccfr", 20, seed, tmp_path)
    s = T.summarize("e2-mccfr", tmp_path)
    assert json.loads((tmp_path / "e2-mccfr-seed1.json").read_text(encoding="utf-8"))["lbr"]["hands"] == T.LBR_HANDS == 4000
    assert s["lbr_stderr_by_seed"] == [0.1, 0.1]
    assert s["runs"] == 2 and s["seeds"] == [1, 2] and s["lbr_bb_mean"] == 1.0 and s["iters"] == 20
    assert (tmp_path / "e2-mccfr-seed1.policy.json").exists()
    assert json.loads((tmp_path / "e2-mccfr-seed1.json").read_text(encoding="utf-8"))["infosets"] > 0


def test_only_allow_listed_jobs_run(tmp_path):
    with pytest.raises(SystemExit, match="unknown job"):
        T.run("rm -rf /", 10, 0, tmp_path)
    with pytest.raises(SystemExit, match="iters"):
        T.run("e2-mccfr", 0, 0, tmp_path)


def test_train_workflow_is_manual_and_passes_inputs_through_env():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "train.yml").read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"}
    text = (ROOT / ".github" / "workflows" / "train.yml").read_text(encoding="utf-8")
    for step in wf["jobs"]["run"]["steps"] + wf["jobs"]["summarize"]["steps"]:
        assert "${{ inputs" not in step.get("run", ""), step  # no inputs interpolated into shell
    assert "secrets." not in text  # CPU training needs no secrets


def _fake_run(folder, seed, **extra):
    (folder / f"e2-mccfr-seed{seed}.json").write_text(json.dumps(
        {"job": "e2-mccfr", "seed": seed, "iters": 10, "iters_per_s": 1.0, "lbr": {"lbr_bb": 0.5}, **extra}), encoding="utf-8")


def test_summary_refuses_unknown_jobs_and_empty_results(tmp_path):
    with pytest.raises(SystemExit, match="unknown job"):
        T.summary_text("../../etc", tmp_path)
    with pytest.raises(SystemExit, match="no successful"):
        T.summary_text("e2-mccfr", tmp_path)
    _fake_run(tmp_path, 1)
    assert json.loads(T.summary_text("e2-mccfr", tmp_path))["runs"] == 1


def test_summary_size_cap(tmp_path, monkeypatch):
    _fake_run(tmp_path, 1)
    monkeypatch.setattr(T, "SUMMARY_MAX_BYTES", 50)
    with pytest.raises(SystemExit, match="bytes >"):
        T.summary_text("e2-mccfr", tmp_path)


@pytest.mark.parametrize("leak", ["ghp_" + "a" * 36, "github_pat_" + "b" * 30, "rpa_" + "C" * 30,
                                  "-----BEGIN RSA PRIVATE KEY-----"])
def test_summary_refuses_credentials(tmp_path, monkeypatch, leak):
    monkeypatch.setattr(T, "summarize", lambda job, folder: {"job": job, "runs": 1, "note": leak})
    with pytest.raises(SystemExit, match="credential"):
        T.summary_text("e2-mccfr", tmp_path)


def test_summary_refuses_secret_env_values(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "not-a-real-value-123")
    monkeypatch.setattr(T, "summarize", lambda job, folder: {"job": job, "runs": 1, "note": "not-a-real-value-123"})
    with pytest.raises(SystemExit, match="RUNPOD_API_KEY"):
        T.summary_text("e2-mccfr", tmp_path)


def test_run_output_size_cap(tmp_path, monkeypatch):
    import referee.e2.lbr as lbr

    monkeypatch.setattr(lbr, "exploitability_lb", lambda pol, hands, seed, abstraction: {"lbr_bb": 1.0, "hands": hands})
    monkeypatch.setattr(T, "ARTIFACT_MAX_BYTES", 100)
    with pytest.raises(SystemExit, match="bytes >"):
        T.run("e2-mccfr", 5, 1, tmp_path)


def test_summarize_step_validates_before_touching_ops():
    text = (ROOT / ".github" / "workflows" / "train.yml").read_text(encoding="utf-8")
    step = text[text.index("- name: summary to ops"):]
    assert step.index("^[a-z0-9-]+$") < step.index("train_jobs summarize") < step.index('mkdir -p "ops/training/$JOB"')


def test_summary_records_the_ref_and_sha_it_ran_on(tmp_path, monkeypatch):
    _fake_run(tmp_path, 1)
    for k in ("GITHUB_REF_NAME", "GITHUB_SHA", "GITHUB_RUN_ID"):
        monkeypatch.delenv(k, raising=False)
    assert {k: T.summarize("e2-mccfr", tmp_path)[k] for k in ("ref", "sha", "run_id")} == {"ref": None, "sha": None, "run_id": None}
    monkeypatch.setenv("GITHUB_REF_NAME", "claude/187-tiers-train")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_RUN_ID", "40624661667")
    s = T.summarize("e2-mccfr", tmp_path)
    assert (s["ref"], s["sha"], s["run_id"]) == ("claude/187-tiers-train", "a" * 40, "40624661667")


@pytest.mark.parametrize("tier,k", [("beginner", 5), ("mid", 11)])
def test_tier_jobs_train_and_are_measured_at_their_tp_resolution(tmp_path, monkeypatch, tier, k):
    import referee.e2.lbr as lbr
    from stalker.e2.abstraction import TIERS

    seen = {}

    def fake_lbr(pol, hands, seed, abstraction):
        seen.update(abstraction=abstraction, seed=seed, hands=hands)
        return {"lbr_bb": 2.0, "stderr_bb": 0.1, "hands": hands}

    monkeypatch.setattr(lbr, "exploitability_lb", fake_lbr)
    T.run(f"e2-tier-{tier}", 20, 3, tmp_path)
    # LBR reads the policy through the tier's own abstraction, on the same deals for every tier.
    assert seen == {"abstraction": TIERS[tier], "seed": 10_000 + 3, "hands": T.LBR_HANDS}
    r = json.loads((tmp_path / f"e2-tier-{tier}-seed3.json").read_text(encoding="utf-8"))
    assert r["tier"] == tier and r["abstraction"] == {"pre_k": k, "post_k": k}
    pol = json.loads((tmp_path / f"e2-tier-{tier}-seed3.policy.json").read_text(encoding="utf-8"))
    assert {int(key.split("|")[2]) for key in pol} <= set(range(k))
    assert T.summarize(f"e2-tier-{tier}", tmp_path)["lbr_bb_mean"] == 2.0


def test_eq_jobs_train_with_the_equity_view(tmp_path, monkeypatch):
    import referee.e2.lbr as lbr

    seen = {}

    def fake_lbr(pol, hands, seed, view):
        seen.update(view=view, seed=seed, hands=hands)
        return {"lbr_bb": 1.5, "stderr_bb": 0.1, "hands": hands}

    monkeypatch.setattr(lbr, "exploitability_lb", fake_lbr)
    T.run("e2-eq-beginner", 3, 1, tmp_path)
    r = json.loads((tmp_path / "e2-eq-beginner-seed1.json").read_text(encoding="utf-8"))
    assert r["view"] == {"view": "equity", "k": 5} and seen["view"].k == 5
    assert seen["seed"] == 10_001 and seen["hands"] == T.LBR_HANDS


def test_e3_job_records_both_policies_and_coverage(tmp_path, monkeypatch):
    import referee.e3.lbr as lbr3

    monkeypatch.setattr(lbr3, "exploitability_lb", lambda pol, hands, seed, k, n, depth: {"lbr_bb": 3.0, "hands": hands})
    T.run("e3-tp-beginner", 2, 1, tmp_path)
    r = json.loads((tmp_path / "e3-tp-beginner-seed1.json").read_text(encoding="utf-8"))
    assert r["players"] == 6 and r["depth"] == "basic" and r["lbr"]["lbr_bb"] == 3.0 and r["coverage"]
    pol = json.loads((tmp_path / "e3-tp-beginner-seed1.policy.json").read_text(encoding="utf-8"))
    assert set(pol) == {"average", "current"}


def test_league_job_records_generations_and_the_champion(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "LEAGUE_GENERATIONS", 2)
    import stalker.e2.league as lg
    from stalker.e2 import personas

    monkeypatch.setattr(lg, "persona_field", lambda names=None: personas.field(("tag",)))
    T.run("e2-league-beginner", 40, 1, tmp_path)
    r = json.loads((tmp_path / "e2-league-beginner-seed1.json").read_text(encoding="utf-8"))
    assert r["tier"] == "beginner" and len(r["generations"]) == 2 and r["iters"] == 40
    assert r["generations"][0]["worst_persona"] == "tag"
    assert r["exploiter"] == {"tier": "beginner", "ratio": 0.5, "strategy": "current"}
    # per_gen = 40 // 2 = 20: max(min(20000, 20), int(0.5 x total)) = max(20, 10), max(20, 20)
    assert [g["exploiter_iters"] for g in r["generations"]] == [20, 20]
    s = T.summarize("e2-league-beginner", tmp_path)
    assert s["runs"] == 1 and len(s["promoted_by_seed"]) == 1 and s["exploiter"]["tier"] == "beginner"
    assert s["exploiter_iters_by_seed"] == [[20, 20]]




def test_league_summary_keeps_one_entry_per_seed(tmp_path):
    # #255: a seed with no promoted champion must stay in place (null), not shift the others.
    for seed, champ in ((1, None), (2, {"gain_bb": 0.4, "field_bb": 0.2, "field_ci95_low_bb": 0.05, "worst_persona": "tag"})):
        (tmp_path / f"e2-league-beginner-seed{seed}.json").write_text(json.dumps(
            {"job": "e2-league-beginner", "seed": seed, "iters": 10, "promoted": int(champ is not None),
             "champion": champ}), encoding="utf-8")
    s = T.summarize("e2-league-beginner", tmp_path)
    assert s["seeds"] == [1, 2]
    assert s["champion_gain_bb_by_seed"] == [None, 0.4] and s["champion_worst_persona_by_seed"] == [None, "tag"]
    assert s["champion_field_ci95_low_bb_by_seed"] == [None, 0.05]
