import importlib.util
import json
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("sufficiency_curve", ROOT / "scripts" / "sufficiency_curve.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

POINT_KEYS = {"games", "decisions", "unclassified", "cells", "lessonable_cells", "s1_rate", "s4_rate", "s5_rate",
              "d1_preliminary", "blocking_cells", "blocking_decision_share", "games_per_half_quantiles", "top_cells",
              "extrapolation", "report_seconds"}


@pytest.fixture(scope="module")
def curve(tmp_path_factory):
    out = tmp_path_factory.mktemp("curve")
    assert sc.main(["--games", "6,12", "--seed", "3", "--out", str(out)]) == 0
    return json.loads((out / "curve.json").read_text(encoding="utf-8"))


def test_curve_schema(curve):
    assert curve["generation"]["games"] == 12 and curve["generation"]["seconds_per_decision"] > 0
    assert [p["games"] for p in curve["points"]] == [6, 12]
    for p in curve["points"]:
        assert set(p) == POINT_KEYS
        assert 0 <= p["s1_rate"] <= 1 and 0 <= p["d1_preliminary"] <= 1
        assert sum(p["blocking_cells"].values()) == p["cells"]
        assert len(p["top_cells"]) == min(sc.TOP_CELLS, p["cells"])
        pred = list(p["extrapolation"]["predicted_d1"].values())
        assert pred == sorted(pred) and 0 <= pred[0] and pred[-1] <= 1 + 1e-9
        assert {"d1_0.5", "d1_0.95", "d1_0.99", "binding", "predicted_d1"} <= set(p["extrapolation"])


def test_prefix_matches_smaller_run(curve):
    # game i is seeded [seed, i], so the 6-game point is the 6-game dataset, with fewer decisions than 12 games
    a, b = curve["points"]
    assert 0 < a["decisions"] < b["decisions"]


def test_required_games_rule_of_three_and_spread():
    # cell in every game with zero spread: only the rule of three binds (60 games per half -> 120)
    assert sc.required_games(100, 100, 0.0) == 120
    # cell in half the games doubles that
    assert sc.required_games(100, 50, 0.0) == 240
    # spread: se scales as 1/sqrt(games), so 4x the allowed se needs 16x the games
    se_half_max = min(sc.SE_MAX.values())
    assert sc.required_games(100, 100, 4 * se_half_max / math.sqrt(2)) == pytest.approx(1600)
    assert sc.required_games(100, 1, 0.0) == math.inf


def test_bad_games_rejected():
    with pytest.raises(SystemExit):
        sc.main(["--games", "1", "--out", "x"])
