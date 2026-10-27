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
    assert json.loads((tmp_path / "e2-mccfr-seed1.json").read_text())["infosets"] > 0


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
    r = json.loads((tmp_path / "e2-tier-beginner-seed1.json").read_text())
    assert r["tier"] == "beginner" and r["abstraction"] == {"pre_k": 5, "post_k": 5}
    pol = json.loads((tmp_path / "e2-tier-beginner-seed1.policy.json").read_text())
    assert {int(k.split("|")[2]) for k in pol} <= set(range(5))
    assert T.summarize("e2-tier-beginner", tmp_path)["lbr_bb_mean"] == 2.0


def test_eq_jobs_train_with_the_equity_view(tmp_path, monkeypatch):
    import referee.e2.lbr as lbr

    seen = {}
    monkeypatch.setattr(lbr, "exploitability_lb", lambda pol, hands, seed, **kw: seen.update(kw) or {"lbr_bb": 1.5})
    T.run("e2-eq-beginner", 3, 1, tmp_path)
    r = json.loads((tmp_path / "e2-eq-beginner-seed1.json").read_text())
    assert r["view"] == {"view": "equity", "k": 5} and seen["view"].k == 5
