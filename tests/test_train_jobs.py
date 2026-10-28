import json

import pytest
import yaml

from stalker import train_jobs as T
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_run_and_summarize_e2_mccfr(tmp_path, monkeypatch):
    import referee.e2.lbr as lbr

    monkeypatch.setattr(lbr, "exploitability_lb", lambda pol, hands, seed: {"lbr_bb": 1.0, "hands": hands})
    for seed in (1, 2):
        T.run("e2-mccfr", 20, seed, tmp_path)
    s = T.summarize("e2-mccfr", tmp_path)
    assert s["runs"] == 2 and s["seeds"] == [1, 2] and s["lbr_bb_mean"] == 1.0 and s["iters"] == 20
    assert (tmp_path / "e2-mccfr-seed1.policy.json").exists()
    assert json.loads((tmp_path / "e2-mccfr-seed1.json").read_text(encoding="utf-8"))["infosets"] > 0
    monkeypatch.setattr(lbr, "exploitability_lb", lambda pol, hands, seed: {"lbr_bb": 1.0, "stderr_bb": 0.1, "hands": hands})
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


def test_tier_jobs_train_at_their_tp_resolution(tmp_path, monkeypatch):
    import referee.e2.lbr as lbr

    monkeypatch.setattr(lbr, "exploitability_lb", lambda pol, hands, seed, **kw: {"lbr_bb": 2.0, "hands": hands})
    T.run("e2-tier-beginner", 20, 1, tmp_path)
    r = json.loads((tmp_path / "e2-tier-beginner-seed1.json").read_text(encoding="utf-8"))
    assert r["tier"] == "beginner" and r["abstraction"] == {"pre_k": 5, "post_k": 5}
    pol = json.loads((tmp_path / "e2-tier-beginner-seed1.policy.json").read_text(encoding="utf-8"))
    assert {int(k.split("|")[2]) for k in pol} <= set(range(5))
    assert T.summarize("e2-tier-beginner", tmp_path)["lbr_bb_mean"] == 2.0


def _fake_run(folder, seed, **extra):
    (folder / f"e2-mccfr-seed{seed}.json").write_text(json.dumps(
        {"job": "e2-mccfr", "seed": seed, "iters": 10, "iters_per_s": 1.0, "lbr": {"lbr_bb": 0.5}, **extra}), encoding="utf-8")
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

    monkeypatch.setattr(lbr, "exploitability_lb", lambda pol, hands, seed, **kw: {"lbr_bb": 1.0, "hands": hands})
    monkeypatch.setattr(lbr, "exploitability_lb", lambda pol, hands, seed: {"lbr_bb": 1.0, "hands": hands})
    monkeypatch.setattr(T, "ARTIFACT_MAX_BYTES", 100)
    with pytest.raises(SystemExit, match="bytes >"):
        T.run("e2-mccfr", 5, 1, tmp_path)


def test_summarize_step_validates_before_touching_ops():
    text = (ROOT / ".github" / "workflows" / "train.yml").read_text(encoding="utf-8")
    step = text[text.index("- name: summary to ops"):]
    assert step.index("^[a-z0-9-]+$") < step.index("train_jobs summarize") < step.index('mkdir -p "ops/training/$JOB"')
