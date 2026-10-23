import numpy as np
import pytest

from stalker.core.cards import HAND_CLASSES, hand_class
from stalker.core.ranges import PREFLOP_TABLE, class_top_pct, preflop_equity, top_range
from stalker.tools.build_tables import build, dumps, main, representative


def test_representative_matches_class():
    for c in HAND_CLASSES:
        assert hand_class(*representative(c)) == c


def test_build_is_deterministic_across_runs_and_workers(tmp_path):
    classes = ["AA", "72o", "AKs"]
    a = build(classes, seed=7, nsim=200, workers=1, max_opp=2)
    b = build(classes, seed=7, nsim=200, workers=2, max_opp=2)
    assert dumps(a) == dumps(b)
    c = build(classes, seed=8, nsim=200, workers=1, max_opp=2)
    assert dumps(a) != dumps(c)


def test_cli_writes_same_file_twice(tmp_path):
    outs = [tmp_path / "a.json", tmp_path / "b.json"]
    for out in outs:
        assert main(["--classes", "KK", "T9s", "--nsim", "100", "--workers", "1", "--out", str(out)]) == 0
    assert outs[0].read_bytes() == outs[1].read_bytes()


def test_cli_rejects_unknown_class(tmp_path):
    assert main(["--classes", "AX", "--out", str(tmp_path / "x.json")]) == 2


def test_committed_table_shape():
    assert PREFLOP_TABLE.exists()
    t = preflop_equity()
    assert list(t) == HAND_CLASSES
    for eqs in t.values():
        assert len(eqs) == 5
        assert all(0.0 < e < 1.0 for e in eqs)
        assert all(x > y for x, y in zip(eqs, eqs[1:]))  # more opponents -> less equity


@pytest.mark.parametrize("cls,expected", [("AA", 0.852), ("72o", 0.346), ("AKs", 0.670)])
def test_committed_table_accuracy(cls, expected):
    assert preflop_equity()[cls][0] == pytest.approx(expected, abs=0.01)


def test_class_top_pct_extremes():
    t = class_top_pct()
    assert min(t, key=t.get) == "AA"
    assert t["72o"] > 0.95
    assert t["32o"] > 0.95


@pytest.mark.parametrize("p", [0.05, 0.2, 0.5])
def test_top_range_mass(p):
    assert top_range(p).sum() / 1326 == pytest.approx(p, abs=0.02)
