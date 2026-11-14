import dataclasses
import json

import numpy as np
import pytest

from stalker.tools.icm_calibration import calibrate, default_config, main
from stalker.tournament.config import winner_take_all
from stalker.tournament.start_state import make_start_state


def _run(tmp_path, seed, name, profile="skewed"):
    out = tmp_path / name
    main(["--players", "6", "--remaining", "3", "--stack-profile", profile, "--games", "8", "--seed", str(seed),
          "--out", str(out)])
    return out.read_bytes()


def test_cli_is_deterministic_per_seed_and_has_the_contract_fields(tmp_path):
    a, b, c = _run(tmp_path, 1, "a.json"), _run(tmp_path, 1, "b.json"), _run(tmp_path, 2, "c.json")
    assert a == b
    da, dc = json.loads(a), json.loads(c)
    assert da["sim_prize_mean"] != dc["sim_prize_mean"]
    for k in ("schema_version", "config", "stacks", "payouts", "icm_equity", "sim_prize_mean", "sim_prize_sd",
              "diff", "games", "seed"):
        assert k in da, k
    assert da["diff"] == pytest.approx([m - e for m, e in zip(da["sim_prize_mean"], da["icm_equity"])], abs=1e-12)


def _calibrate(cfg, remaining, profile, games=6, seed=0):
    rng = np.random.default_rng(seed)
    ss = make_start_state(cfg, rng, remaining, profile, 2)
    return calibrate(cfg, ss, None, games, rng)


@pytest.mark.parametrize("profile", ["random", "skewed"])
def test_prize_and_equity_both_sum_to_the_pool(profile):
    cfg = default_config(6)
    out = _calibrate(cfg, 3, profile)
    assert out["prize_pool"] == pytest.approx(cfg.prize_pool, abs=1e-9)
    assert sum(out["sim_prize_mean"]) == pytest.approx(cfg.prize_pool, abs=1e-9)
    assert sum(out["icm_equity"]) == pytest.approx(cfg.prize_pool, abs=1e-9)


def test_even_stacks_split_equity_equally():
    cfg = default_config(6)
    out = _calibrate(cfg, 4, "even", games=2)
    assert len(set(out["stacks"])) == 1
    assert out["icm_equity"] == pytest.approx([cfg.prize_pool / 4] * 4, abs=1e-9)


def test_winner_take_all_equity_is_chip_proportional():
    cfg = dataclasses.replace(default_config(6), payouts=winner_take_all())
    out = _calibrate(cfg, 3, "skewed", games=2)
    total = sum(out["stacks"])
    assert out["icm_equity"] == pytest.approx([cfg.prize_pool * s / total for s in out["stacks"]], abs=1e-9)
    assert sum(out["sim_prize_mean"]) == pytest.approx(cfg.prize_pool, abs=1e-9)


def _cli(tmp_path, name, *extra, games=8):
    out = tmp_path / name
    main(["--players", "6", "--remaining", "3", "--stack-profile", "skewed", "--games", str(games), "--seed", "3",
          "--out", str(out), *extra])
    return out.read_bytes()


def test_persona_agents_are_deterministic_and_differ_from_random(tmp_path):
    a = _cli(tmp_path, "a.json", "--agents", "persona:tag")
    b = _cli(tmp_path, "b.json", "--agents", "persona:tag")
    r = _cli(tmp_path, "r.json")
    assert a == b
    da, dr = json.loads(a), json.loads(r)
    assert da["agents"] == "persona:tag" and dr["agents"] == "random"
    assert da["schema_version"] == 2
    assert da["sim_prize_mean"] != dr["sim_prize_mean"]
    assert sum(da["sim_prize_mean"]) == pytest.approx(da["prize_pool"], abs=1e-9)


def test_diff_se_and_z_follow_the_formula(tmp_path):
    d = json.loads(_cli(tmp_path, "s.json"))
    se = [sd / d["games"] ** 0.5 for sd in d["sim_prize_sd"]]
    assert d["diff_se"] == pytest.approx(se, abs=1e-12)
    assert d["z"] == pytest.approx([x / s if s else 0.0 for x, s in zip(d["diff"], se)], abs=1e-12)
    one = json.loads(_cli(tmp_path, "one.json", games=1))
    assert one["diff_se"] == [0.0] * 3 and one["z"] == [0.0] * 3


def test_unknown_persona_exits_nonzero(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        main(["--players", "6", "--remaining", "3", "--agents", "persona:nope", "--out", str(tmp_path / "x.json")])
    assert e.value.code != 0
    assert "unknown persona" in capsys.readouterr().err
    assert not (tmp_path / "x.json").exists()
