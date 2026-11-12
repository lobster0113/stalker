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
        # ADR 0024 raised only the 3-player lbr seeds (v2); every other cell is still the ADR 0020 table
        want_lbr = 2 if n == "3" else int(mc)
        assert spec["min_seeds"] == {"lbr": want_lbr, "lbr_average": int(ma)}


def test_v1_frozen_and_v2_differs_only_in_three_player_min_seeds():
    raw = T.THRESHOLDS_V1.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == T.THRESHOLDS_V1_SHA256
    v1, v2 = json.loads(raw), T.load_thresholds()
    assert v1["players"]["3"]["min_seeds"]["lbr"] == 1 and v2["players"]["3"]["min_seeds"]["lbr"] == 2
    v1["players"]["3"]["min_seeds"]["lbr"] = 2
    for doc in (v1, v2):
        doc.pop("adr"), doc.pop("note")
    assert v1 == v2


def test_three_player_single_seed_is_insufficient():
    r = T.judge([summ(1, 3, 2000, 4.0)])
    assert r["3"]["lbr"]["verdict"] == "insufficient" and r["3"]["lbr"]["seeds"] == 1
    assert T.judge([summ(1, 3, 2000, 4.0), summ(2, 3, 2000, 4.0)])["3"]["lbr"]["verdict"] == "pass"


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


def write_results(d, items):
    d.mkdir(parents=True, exist_ok=True)
    for run, s in items:
        (d / f"{run}.summary.json").write_text(json.dumps(s), encoding="utf-8")
    return d


def test_json_output_keys(tmp_path, capsys):
    f = tmp_path / "a.json"
    f.write_text(json.dumps(summ(1, 2, 2000, 7.1)), encoding="utf-8")
    assert T.main(["--json", str(f)]) == 0
    out = json.loads(capsys.readouterr().out)["players"]
    assert set(out) == {"2", "3", "4", "5", "6"} and set(out["2"]) == {"lbr", "lbr_average"}
    assert out["2"]["lbr"] == {"verdict": "pass", "seeds": 1, "mean_lbr_bb": 7.1, "limit": 9.0}
    assert out["2"]["lbr_average"] == {"verdict": "insufficient", "seeds": 0, "mean_lbr_bb": None, "limit": 8.7}
    assert out["6"]["lbr"]["verdict"] == "insufficient"


def test_collect_one_job_latest_run_per_seed(tmp_path):
    d = write_results(tmp_path / "results", [
        ("10", summ(1, 2, 2000, 9.5)), ("12", summ(1, 2, 2000, 7.0)),  # seed 1 rerun: 12 supersedes 10
        ("11", summ(2, 2, 2000, 8.0)),
        ("13", {**summ(3, 2, 2000, 1.0), "job": "other"}),             # another job: never mixed in
        ("14", {"seed": 4, "job": "j", "lbr": {"lbr_bb": 1.0}})])      # no by_players: skipped
    (d / "notes.json").write_text("not json", encoding="utf-8")       # not a <run id> result: ignored
    runs = T.collect(d, "j")
    assert [r for r, _ in runs] == ["11", "12"]
    rec = T.verdict("j", d)
    assert rec["runs"] == ["11", "12"] and rec["seeds"] == [2, 1] and rec["job"] == "j"
    assert rec["players"]["2"]["lbr"] == {"verdict": "pass", "seeds": 2, "mean_lbr_bb": 7.5, "limit": 9.0}
    assert rec["thresholds_sha256"] == T.THRESHOLDS_SHA256
    assert T.main(["--job", "j", "--results-dir", str(d)]) == 0
    with pytest.raises(T.ThresholdError, match="no results"):
        T.verdict("missing", d)
    assert T.main(["--job", "j"]) == 2 and T.main(["--job", "j", "--results-dir", str(d), "x.json"]) == 2


def test_record_never_raises(tmp_path):
    d = write_results(tmp_path / "results", [("1", summ(1, 6, 1000, 2.8)), ("2", summ(2, 6, 1000, 2.8))])
    out, logs = tmp_path / "verdicts", []
    rec = T.record("j", d, out, log=logs.append)
    assert rec["players"]["6"]["lbr"]["verdict"] == "fail" and "fail 6p lbr" in logs[-1]
    assert json.loads((out / "j.json").read_text(encoding="utf-8")) == rec
    (d / "3.json").write_text("{broken", encoding="utf-8")
    rec = T.record("j", d, out, log=logs.append)
    assert "unreadable" in rec["error"] and "players" not in rec
    assert json.loads((out / "j.json").read_text(encoding="utf-8"))["error"] == rec["error"]
    assert "error" in T.record("../x", d, out, log=logs.append) and not (tmp_path / "x.json").exists()


def test_real_mixn_c1_verdict_record_passes(tmp_path):
    items = json.loads(FIX.read_text(encoding="utf-8"))
    assert sorted(s["run"] for s in items) == ["41812635702", "41812640240", "41813684540"]
    d = write_results(tmp_path / "results", [(s["run"], s) for s in items])
    rec = T.record("e3-tp-mid-c1-mixn-pod", d, tmp_path / "verdicts", log=lambda _m: None)
    assert rec["runs"] == ["41812635702", "41812640240", "41813684540"]
    for n in ("2", "3", "4", "5", "6"):
        for kind in T.KINDS:
            assert rec["players"][n][kind]["verdict"] == "pass", (n, kind)


# --- ADR 0025: lbr_thresholds_v3.json judges the AIVAT-corrected column of web policy LBR results ---
WEB_FIX = Path(__file__).parent / "fixtures" / "web_policy_lbr_43111293721.json"
ADR25 = Path(__file__).parents[1] / "docs/decisions/0025-aivat-lbr-thresholds.md"


def v3():
    return T.load_thresholds(*T.TABLES["v3"])


def test_every_table_pinned_and_v3_differs_from_v2_only_in_column_and_min_seeds():
    for path, pin in T.TABLES.values():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pin, path.name
    old, new = T.load_thresholds(), v3()
    assert "column" not in old and new["column"] == "aivat_lbr_bb"
    for n, spec in old["players"].items():
        got = new["players"][n]
        assert {k: got[k] for k in ("lbr_max", "lbr_average_max", "hands")} == \
               {k: spec[k] for k in ("lbr_max", "lbr_average_max", "hands")}
        assert got["min_seeds"] == {"lbr": 1, "lbr_average": spec["min_seeds"]["lbr_average"]}
    assert "lbr_thresholds_v3.json" in ADR25.read_text(encoding="utf-8")


def test_edited_table_is_refused(tmp_path):
    f = tmp_path / "lbr_thresholds_v3.json"
    f.write_bytes(T.THRESHOLDS_V3.read_bytes().replace(b"9.0", b"9.5"))
    with pytest.raises(T.ThresholdError, match="sha256"):
        T.load_thresholds(f, T.THRESHOLDS_V3_SHA256)


def aiv(seed, n, hands, raw, corrected):
    s = summ(seed, n, hands, raw)
    s["by_players"][str(n)]["lbr"]["aivat_lbr_bb"] = corrected
    return s


def test_v3_judges_the_corrected_column():
    # (a) raw 2.8 would fail the 6p line 2.7; the corrected 2.6 passes, and one seed is enough under v3
    r = T.judge([aiv(1, 6, 1000, 2.8, 2.6)], v3())
    assert r["6"]["lbr"] == {"verdict": "pass", "mean": 2.6, "limit": 2.7, "seeds": 1}
    assert T.judge([aiv(1, 6, 1000, 2.6, 2.8)], v3())["6"]["lbr"]["verdict"] == "fail"
    # (c) the same summaries under v2 read lbr_bb as before
    for s in ([aiv(1, 6, 1000, 2.8, 2.6), aiv(2, 6, 1000, 2.8, 2.6)], [summ(1, 2, 2000, 7.1)]):
        plain = [json.loads(json.dumps(x)) for x in s]
        for x in plain:
            for cell in x["by_players"].values():
                cell["lbr"].pop("aivat_lbr_bb", None)
        assert T.judge(s, T.load_thresholds()) == T.judge(plain) == T.judge(s)
    assert T.judge([aiv(1, 6, 1000, 2.8, 2.6), aiv(2, 6, 1000, 2.8, 2.6)])["6"]["lbr"]["verdict"] == "fail"


def test_v3_without_the_corrected_column_says_how_to_fix():
    # (b) a schema-1 cell at the judged hand count is an input error, not a quiet `insufficient`
    with pytest.raises(T.ThresholdError, match="--aivat-samples 8"):
        T.judge([summ(1, 2, 2000, 7.1)], v3())
    # a cell at another hand count is not judged, so it needs no column
    assert T.judge([summ(1, 2, 600, 7.1)], v3())["2"]["lbr"]["verdict"] == "insufficient"


def test_record_stays_record_only_on_v2(tmp_path):
    d = write_results(tmp_path / "results", [("1", summ(1, 2, 2000, 7.1))])
    rec = T.record("j", d, tmp_path / "verdicts", log=lambda _m: None)
    assert rec["thresholds"] == "lbr_thresholds_v2.json" and rec["players"]["2"]["lbr"]["verdict"] == "pass"


def web_doc(rows, legacy=()):
    return {"schema": T.WEB_SCHEMA, "schema_version": 2, "legacy_pages": list(legacy), "rows": rows}


def row(n, seed, backoff, raw, corrected=None, hands=2000):
    r = {"players": n, "seed": seed, "backoff": backoff, "hands": hands, "lbr_bb": raw}
    return r if corrected is None else {**r, "aivat_lbr_bb": corrected}


def test_from_web_result_takes_service_cells():
    doc = web_doc([row(2, 1, True, 6.0, 5.0), row(2, 1, False, 9.9, 9.9),
                   row(6, 1, False, 0.8, 0.7, 1000), row(2, 2, True, 6.2, 5.2)], legacy=[6])
    s = T.from_web_result(doc)
    assert s == [{"seed": 1, "by_players": {"2": {"lbr": {"hands": 2000, "lbr_bb": 6.0, "aivat_lbr_bb": 5.0}},
                                           "6": {"lbr": {"hands": 1000, "lbr_bb": 0.8, "aivat_lbr_bb": 0.7}}}},
                 {"seed": 2, "by_players": {"2": {"lbr": {"hands": 2000, "lbr_bb": 6.2, "aivat_lbr_bb": 5.2}}}}]
    r = T.judge(s, v3())
    assert r["2"]["lbr"]["mean"] == pytest.approx(5.1) and r["6"]["lbr"]["verdict"] == "pass"
    with pytest.raises(T.ThresholdError, match="no service rows"):
        T.from_web_result(web_doc([row(2, 1, False, 6.0)]))
    with pytest.raises(T.ThresholdError, match="not a"):
        T.from_web_result({"rows": []})


def test_ci_run_43111293721_passes_v3_on_every_service_cell(capsys):
    assert T.main(["--json", str(WEB_FIX)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["thresholds"] == "lbr_thresholds_v3.json" and out["column"] == "aivat_lbr_bb"
    means = {"2": 5.781, "3": 4.677, "4": 2.646, "5": 1.950, "6": 0.766}   # research doc, 「CI 측정」 (on; 6p legacy off)
    for n, m in means.items():
        cell = out["players"][n]["lbr"]
        assert cell["verdict"] == "pass" and cell["seeds"] == 8 and cell["mean_lbr_bb"] == pytest.approx(m, abs=6e-4)
        assert out["players"][n]["lbr_average"]["verdict"] == "insufficient"   # the web job measures current LBR only
    assert T.main(["--thresholds", "v2", str(WEB_FIX)]) == 0
    assert "1.547" in capsys.readouterr().out   # 5p on, raw column


def test_cli_refuses_mixed_inputs_and_v3_on_job(tmp_path, capsys):
    f = tmp_path / "s.json"
    f.write_text(json.dumps(summ(1, 2, 2000, 7.1)), encoding="utf-8")
    assert T.main([str(WEB_FIX), str(f)]) == 2 and "mix" in capsys.readouterr().err
    assert T.main(["--thresholds", "v3", "--job", "j", "--results-dir", str(tmp_path)]) == 2
    assert T.main(["--thresholds", "v3", str(f)]) == 2 and "--aivat-samples 8" in capsys.readouterr().err
