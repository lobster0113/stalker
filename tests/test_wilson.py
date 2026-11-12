import pytest

from stalker.tools import phh_stats as P
from stalker.tools import web_hit_rate as H
from stalker.tools.wilson import wilson95


def test_wilson95_matches_the_790_bound_and_its_edges():
    lo, hi = wilson95(14, 143)
    assert hi == pytest.approx(0.1576, abs=5e-4) and lo == pytest.approx(0.0592, abs=5e-4)
    lo0, hi0 = wilson95(0, 10)
    assert lo0 == 0.0 and 0 < hi0 < 1
    lon, hin = wilson95(10, 10)
    assert hin == pytest.approx(1.0) and hin <= 1.0 and 0 < lon < 1
    assert wilson95(0, 0) is None


def test_phh_stats_percent_interval_is_the_shared_one():
    lo, hi = wilson95(14, 143)
    assert P._wilson(14, 143) == [round(100 * lo, 1), round(100 * hi, 1)] == [5.9, 15.8]
    assert P._wilson(3, 0) is None


def test_uniform_ci95_is_the_uniform_share_rounded_to_six_decimals():
    assert H.uniform_ci95({"decisions": 143, "uniform": 14}) == [0.059217, 0.157626]
    assert H.uniform_ci95({"decisions": 0, "uniform": 0}) is None
    assert H.uniform_ci95({"decisions": 7, "uniform": 0})[0] == 0.0
    assert H.uniform_ci95({"decisions": 7, "uniform": 7})[1] == 1.0
