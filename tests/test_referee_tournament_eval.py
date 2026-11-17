"""Referee tournament evaluation (#911): determinism, cell-keyed seeds, lambda, backoff counts, CLI stamp."""
from __future__ import annotations

import json

import pytest

from referee.e3 import tournament_eval as TE
from stalker.agents.e3_policy import PolicyTable

EMPTY = PolicyTable({}, k=5, depth="basic", menu="v1", raise_cap=3)   # every decision backs off to the rule bot
PRESET = "9max_sng_503020"


def spot(profile="even", remaining=4, level_index=0):
    return {"preset": PRESET, "remaining": remaining, "profile": profile, "level_index": level_index}


def dumps(x):
    return json.dumps(x, sort_keys=True)


def test_spot_file_v1_is_the_first_stage():
    spots = TE.load_spots()
    assert spots == [spot("even"), spot("random"), spot("skewed")]


@pytest.mark.parametrize("kwargs,match", [
    ({"games": 1}, "games=1"),
    ({"seed": 10000}, "10001"),
    ({"lam": 1.5}, "lam"),
    ({"spots": []}, "no spots"),
    ({"spots": [spot("flat")]}, "profile"),
    ({"spots": [spot(), spot()]}, "twice"),
    ({"spots": [{"preset": PRESET}]}, "missing"),
    ({"spots": [spot(remaining=10)]}, "remaining"),
    ({"field": "policy:x"}, "field"),
])
def test_bad_arguments_fail_before_any_game(kwargs, match):
    args = {"spots": [spot()], "games": 2, "seed": 10001, "field": "persona:tag", "lam": 0.0, **kwargs}
    with pytest.raises(ValueError, match=match):
        TE.evaluate_tournament(EMPTY, **args)


@pytest.mark.slow
def test_same_inputs_give_identical_bytes_and_cells_are_seeded_by_key():
    both = TE.evaluate_tournament(EMPTY, [spot("even"), spot("skewed")], games=2, seed=10001)
    again = TE.evaluate_tournament(EMPTY, [spot("even"), spot("skewed")], games=2, seed=10001)
    assert dumps(both) == dumps(again)
    alone = TE.evaluate_tournament(EMPTY, [spot("skewed")], games=2, seed=10001)
    assert dumps(alone["cells"][0]) == dumps(both["cells"][1])
    other = TE.evaluate_tournament(EMPTY, [spot("skewed")], games=2, seed=10002)
    assert dumps(other["cells"][0]) != dumps(alone["cells"][0])


@pytest.mark.slow
def test_lambda_zero_is_pure_icm_and_the_correction_is_bubble_only():
    (c0,) = TE.evaluate_tournament(EMPTY, [spot("skewed")], games=2, lam=0.0)["cells"]
    assert c0["bubble"] and c0["corrected_equity"]["mean"] == c0["icm_equity"]["mean"]
    (c1,) = TE.evaluate_tournament(EMPTY, [spot("skewed")], games=2, lam=0.5)["cells"]
    assert c1["corrected_equity"]["mean"] != c1["icm_equity"]["mean"]
    assert c1["icm_equity"] == c0["icm_equity"] and c1["sim_prize"] == c0["sim_prize"]
    (off,) = TE.evaluate_tournament(EMPTY, [spot("skewed", remaining=5)], games=2, lam=0.5)["cells"]
    assert not off["bubble"]
    assert off["corrected_equity"]["mean"] == off["icm_equity"]["mean"]


@pytest.mark.slow
def test_cell_fields_are_prize_pool_fractions_and_backoffs_are_counted():
    out = TE.evaluate_tournament(EMPTY, [spot("random")], games=3, lam=0.2)
    assert out["unit"] == "prize_pool_fraction" and out["schema_version"] == TE.SCHEMA_VERSION
    (c,) = out["cells"]
    assert 0.0 <= c["sim_prize"]["mean"] <= 1.0 and c["sim_prize"]["se"] >= 0.0
    assert c["sim_minus_corrected"]["mean"] == pytest.approx(c["sim_prize"]["mean"] - c["corrected_equity"]["mean"])
    assert c["sim_minus_corrected"]["se"] == pytest.approx(c["sim_prize"]["se"])
    p = c["policy"]
    assert p["decisions"] > 0 and p["backoffs"] == p["decisions"] and p["policy_hits"] == 0
    assert p["backoff_rate"] == 1.0 and sum(p["backoff_reasons"].values()) == p["backoffs"]


def _write_policy(path, train_env=None):
    doc = {"q": 1000, "k": 5, "depth": "basic", "menu": "v1", "raise_cap": 3, "key_variant": "c1", "policy": {}}
    if train_env:
        doc["model"] = {"train_env": train_env}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


@pytest.mark.slow
def test_cli_smoke_stamps_inputs(tmp_path):
    env = {"env_id": "x", "stage": "b", "level_index": 0, "lam": 0.25, "stacks": "bubble:skewed"}
    pol = _write_policy(tmp_path / "p.json", env)
    spots = tmp_path / "spots.json"
    spots.write_text(json.dumps({"spots": [spot("skewed")]}), encoding="utf-8")
    out = tmp_path / "eval.json"
    assert TE.main(["--policy", str(pol), "--spots", str(spots), "--games", "2", "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["schema_version"] == TE.SCHEMA_VERSION and doc["train_env"] == env
    assert doc["lam"] == 0.25 and doc["lam_source"] == "train_env"
    assert len(doc["policy"]["sha256"]) == 64 and len(doc["spots"]["sha256"]) == 64
    assert TE.main(["--policy", str(pol), "--spots", str(spots), "--games", "2", "--out", str(tmp_path / "b.json")]) == 0
    assert (tmp_path / "b.json").read_bytes() == out.read_bytes()


def test_policy_without_train_env_uses_lambda_zero(tmp_path):
    assert TE.read_train_env(_write_policy(tmp_path / "p.json")) is None


def test_cli_rejects_low_seed(tmp_path, capsys):
    pol = _write_policy(tmp_path / "p.json")
    with pytest.raises(SystemExit) as e:
        TE.main(["--policy", str(pol), "--seed", "1"])
    assert e.value.code == 2 and "10001" in capsys.readouterr().err


class _Agent:
    def __init__(self, c):
        self._c = c

    def counts(self):
        return self._c


def test_counts_sums_by_street_and_tolerates_old_agents():
    a = {"decisions": 5, "policy_hits": 3, "backoffs": 2, "backoff_reasons": {"no_key": 2},
         "by_street": {"0": {"decisions": 3, "policy_hits": 2}, "1": {"decisions": 2, "policy_hits": 1}}}
    b = {"decisions": 2, "policy_hits": 2, "backoffs": 0, "backoff_reasons": {},
         "by_street": {"0": {"decisions": 2, "policy_hits": 2}}}
    out = TE._counts([_Agent(a), _Agent(b)])
    bs = out["by_street"]
    assert bs["0"] == {"decisions": 5, "policy_hits": 4, "hit_rate": 0.8}
    assert bs["1"]["hit_rate"] == 0.5
    assert sum(v["decisions"] for v in bs.values()) == out["decisions"]
    assert sum(v["policy_hits"] for v in bs.values()) == out["policy_hits"]
    old = {k: v for k, v in a.items() if k != "by_street"}
    o2 = TE._counts([_Agent(old)])
    assert o2["by_street"] == {} and o2["backoff_rate"] == 0.4
