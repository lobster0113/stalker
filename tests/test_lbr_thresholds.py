import hashlib
import json
import re
from pathlib import Path

import pytest

from referee.e3 import thresholds as T

FIX = Path(__file__).parent / "fixtures" / "lbr_by_players_mixn_c1.json"
ADR = Path(__file__).parents[1] / "docs/decisions/0020-short-handed-lbr-thresholds.md"


def summ(seed, n, hands, cur, avg=None, **extra):
    cell = {"lbr": {"lbr_bb": cur, "stderr_bb": 1.0, "hands": hands}}
    if avg is not None:
        cell["lbr_average"] = {"lbr_bb": avg, "stderr_bb": 1.0, "hands": hands}
    return {"seed": seed, "job": "j", "by_players": {str(n): cell}, **extra}


def test_pinned_and_matches_adr_table():
    assert hashlib.sha256(T.THRESHOLDS.read_bytes()).hexdigest() == T.THRESHOLDS_SHA256
    rows = re.findall(r"^\| (\d) \| ([\d.]+) \| ([\d.]+) \| (\d+) \| (\d) / (\d) \|$", ADR.read_text(encoding="utf-8"), re.M)
    assert len(rows) == 5
    table = T.load_thresholds()["players"]
    for n, cur, avg, hands, mc, ma in rows:
        spec = table[n]
        assert (spec["lbr_max"], spec["lbr_average_max"], spec["hands"]) == (float(cur), float(avg), int(hands))
        assert spec["min_seeds"] == {"lbr": int(mc), "lbr_average": int(ma)}


def test_synthetic_cases():
    r = T.judge([summ(1, 2, 2000, 7.1)])
    assert r["2"]["lbr"]["verdict"] == "pass" and r["2"]["lbr_average"]["verdict"] == "insufficient"
    assert T.judge([summ(1, 2, 600, 9.698)])["2"]["lbr"]["verdict"] == "insufficient"
    assert T.judge([summ(1, 6, 1000, 2.8), summ(2, 6, 1000, 2.8)])["6"]["lbr"]["verdict"] == "fail"
    assert T.judge([summ(1, 4, 600, 9.0)])["4"]["lbr"]["verdict"] == "insufficient"


def test_rejects_duplicates_and_mixes():
    with pytest.raises(T.ThresholdError, match="duplicate seed"):
        T.judge([summ(1, 2, 2000, 7), summ(1, 2, 2000, 7)])
    with pytest.raises(T.ThresholdError, match="job"):
        T.judge([summ(1, 2, 2000, 7), {**summ(2, 2, 2000, 7), "job": "other"}])
    with pytest.raises(T.ThresholdError, match="policy"):
        T.judge([summ(1, 2, 2000, 7, policy="a"), summ(2, 2, 2000, 7, policy="b")])
    with pytest.raises(T.ThresholdError, match="no summaries"):
        T.judge([])


def test_real_mixn_c1_runs():
    r = T.judge(json.loads(FIX.read_text(encoding="utf-8")))
    for n in ("2", "3"):
        assert r[n]["lbr"]["verdict"] == r[n]["lbr_average"]["verdict"] == "pass"
    # the three runs' hand counts equal the ADR table for 4-6 players, so those are judged too
    for n in ("4", "5", "6"):
        assert r[n]["lbr"]["seeds"] == 3 and r[n]["lbr"]["verdict"] == "pass"


def test_cli_exit_codes(tmp_path, capsys):
    ok, bad = tmp_path / "ok.json", tmp_path / "bad.json"
    ok.write_text(json.dumps(summ(1, 2, 2000, 7.1)), encoding="utf-8")
    bad.write_text(json.dumps(summ(1, 2, 2000, 9.5)), encoding="utf-8")
    assert T.main([str(ok)]) == 0
    assert "insufficient" in capsys.readouterr().out
    assert T.main([str(bad)]) == 1
    assert "fail" in capsys.readouterr().out
    assert T.main([]) == 2
