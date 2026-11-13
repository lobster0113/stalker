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
