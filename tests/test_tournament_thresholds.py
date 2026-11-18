import copy
import json

import pytest

from referee.e3 import tournament_thresholds as tt

ARGS = {"presets": ["9max_sng_503020"], "remaining": [4], "profiles": ["even", "random", "skewed"],
        "level_indexes": [0], "layouts": 3, "games": 400, "sym_games": 200, "seed": 10001, "field": "persona:tag"}


def res(a, b, mean, se):
    return {"args": dict(ARGS), "agents": {"A": {"sha256": a}, "B": {"sha256": b}},
            "primary": {"mean": mean, "se": se}}


# ADR 0030 evidence 1: runs 43882446641, 44000780867, 44005595416 (minimal fields copied from ops:cloud/results).
REAL = [res("f6d7acb1", "2334f58c", 0.0012777777777777761, 0.002853655259484889),
        res("2e9d38f9", "b0f26a24", 0.0007222222222222222, 0.002818171905072033),
        res("260d68b3", "422c8fae", -0.001888888888888889, 0.002886357415377511)]


def test_real_runs_pass():
    out = tt.judge(REAL)
    assert out["verdict"] == "pass" and out["pairs"] == 3 and out["limit"] == -0.0075
    assert out["ci_low"] > -0.0075


def test_boundary_mean_fails():
    out = tt.judge([res(f"a{i}", f"b{i}", -0.0075, 0.0029) for i in range(3)])
    assert out["verdict"] == "fail"


@pytest.mark.parametrize("k", [1, 2])
def test_too_few_pairs_insufficient(k):
    assert tt.judge(REAL[:k])["verdict"] == "insufficient"


def test_duplicate_pair_error():
    with pytest.raises(tt.ThresholdError, match="twice"):
        tt.judge([REAL[0], REAL[0], REAL[1]])


def test_missing_primary_error():
    bad = copy.deepcopy(REAL)
    del bad[1]["primary"]
    with pytest.raises(tt.ThresholdError, match="primary"):
        tt.judge(bad)


@pytest.mark.parametrize("key,val", [("remaining", [3]), ("games", 100), ("seed", 5), ("presets", ["x"])])
def test_mixed_config_error(key, val):
    bad = copy.deepcopy(REAL)
    bad[2]["args"][key] = val
    with pytest.raises(tt.ThresholdError, match=key):
        tt.judge(bad)


def test_pinned_table_edit_rejected(tmp_path):
    p = tmp_path / "t.json"
    p.write_bytes(tt.THRESHOLDS.read_bytes() + b" ")
    with pytest.raises(tt.ThresholdError, match="sha256"):
        tt.load_thresholds(p)


def test_cli_exit_codes(tmp_path, capsys):
    def write(rs):
        paths = []
        for i, r in enumerate(rs):
            p = tmp_path / f"{i}.json"
            p.write_text(json.dumps(r), encoding="utf-8")
            paths.append(str(p))
        return paths

    assert tt.main(["--json", *write(REAL)]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "pass"
    assert tt.main(write(REAL[:1])) == 0
    assert tt.main(write([res(f"a{i}", f"b{i}", -0.0075, 0.0029) for i in range(3)])) == 1


# --- recheck (#983, ADR 0030 되돌리는 조건) ---
def _three(means, se=0.003):
    return [res(f"a{i}", f"b{i}", m, se) for i, m in enumerate(means)]


def test_recheck_ok_inside_boundary():
    out = tt.recheck(_three([0.001, 0.0, -0.001]))
    assert out["status"] == "ok" and out["overlap"] is True and out["ratio"] < 2 and out["pairs"] == 3


def test_recheck_sd_above_twice_se():
    out = tt.recheck(_three([0.02, 0.0, -0.02], se=0.003))
    assert out["status"] == "recheck" and out["between_sd"] > 2 * out["within_se"]


def test_recheck_disjoint_cis_with_small_sd():
    # sd 0.0075 < 2*se 0.0076 but pair 0 and 1 CIs (+-1.96*0.0038) are disjoint (gap 0.015 > 0.0149)
    out = tt.recheck(_three([0.0075, -0.0075, 0.0], se=0.0038))
    assert out["between_sd"] <= 2 * out["within_se"] and out["overlap"] is False and out["status"] == "recheck"


def test_recheck_two_pairs_insufficient():
    assert tt.recheck(REAL[:2])["status"] == "insufficient"


def test_recheck_real_runs_ok():
    assert tt.recheck(REAL)["status"] == "ok"


def test_recheck_input_errors():
    with pytest.raises(tt.ThresholdError):
        tt.recheck([REAL[0], REAL[0], REAL[1]])


def _ops(tmp_path, docs, history):
    import subprocess
    origin = tmp_path / "origin"
    (origin / "cloud" / "results").mkdir(parents=True)
    (origin / "metrics").mkdir()
    for n, d in docs.items():
        (origin / "cloud" / "results" / f"{n}.json").write_text(json.dumps(d), encoding="utf-8")
    (origin / "metrics" / "history.jsonl").write_text(history, encoding="utf-8")
    run = lambda cwd, *a: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)
    run(origin, "init", "-q", "-b", "ops")
    run(origin, "add", "-A")
    run(origin, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "ops")
    clone = tmp_path / "clone"
    run(tmp_path, "clone", "-q", "--no-checkout", str(origin), str(clone))
    return clone


def test_recheck_cli_reads_history_and_ops(tmp_path, capsys):
    docs = {100 + i: dict(r, primary={"metric": "learner sim prize - ICM equity (B - A)", **r["primary"]})
            for i, r in enumerate(REAL)}
    row = json.dumps({"sha": "x", "ts": "t", "tournament_verdict": "pass", "tournament_runs": [100, 101, 102],
                      "tournament_primary_ci_low": 0, "tournament_primary_mean": 0, "tournament_pairs": 3})
    clone = _ops(tmp_path, docs, row + "\n" + json.dumps({"sha": "y"}) + "\n")
    assert tt.recheck_from_ops(repo=clone)["status"] == "ok"
    out = tt.recheck_from_ops(history=json.dumps({"sha": "z"}), repo=clone)
    assert out["status"] == "insufficient" and "error" in out
    h = tmp_path / "h.jsonl"
    h.write_text("{}\n", encoding="utf-8")
    assert tt.main(["--recheck", "--history", str(h)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "insufficient"
