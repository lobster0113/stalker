"""Demo record export/import validation (#117): run the page's own parseRecords in node."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEMO = (Path(__file__).resolve().parent.parent / "web" / "demo" / "index.html").read_text(encoding="utf-8")


def _parse(texts: list[str]) -> list[dict]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed; parseRecords is plain JS")
    const = re.search(r"^const RECORDS_SCHEMA = .*?;$", DEMO, re.M).group(0)
    fn = re.search(r"^function parseRecords\(text\) \{.*?^\}", DEMO, re.S | re.M).group(0)
    js = f"{const}\n{fn}\nfor (const t of {json.dumps(texts)}) console.log(JSON.stringify(parseRecords(t)));"
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return [json.loads(line) for line in out.splitlines()]


def test_valid_export_parses_and_bad_input_says_how_to_fix():
    good = {"schema": "stalker.demo.records", "schema_version": 1, "weak": {"hand.equity": {"n": 3, "sum": 210}},
            "itimes": [4.2, 7.0], "rankq": {"n": 1, "sum": 80}}
    newer = dict(good, schema_version=3)
    bad_weak = dict(good, weak={"hand.equity": {"n": "x"}})
    res = _parse([json.dumps(good), "{oops", json.dumps({"schema": "other"}), json.dumps(newer), json.dumps(bad_weak),
                  json.dumps(dict(good, itimes=[-1]))])
    assert res[0]["data"]["weak"] == good["weak"] and res[0]["data"]["itimes"] == [4.2, 7.0]
    assert "그대로 붙여넣으세요" in res[1]["error"]
    assert "schema" in res[2]["error"]
    assert "새로 고친 뒤" in res[3]["error"]
    assert "weak" in res[4]["error"] and "itimes" in res[5]["error"]


def test_weak_items_need_at_least_one_answer():
    base = {"schema": "stalker.demo.records", "schema_version": 1}
    zero, ok_rankq = _parse([json.dumps(dict(base, weak={"hand.equity": {"n": 0, "sum": 0}})),
                             json.dumps(dict(base, rankq={"n": 0, "sum": 0}))])
    assert "n ≥ 1" in zero["error"] and "data" in ok_rankq


def test_missing_fields_default_to_empty_records():
    (r,) = _parse([json.dumps({"schema": "stalker.demo.records", "schema_version": 1})])
    assert r["data"] == {"weak": {}, "itimes": [], "rankq": {"n": 0, "sum": 0}, "eqab": []}


def test_v2_question_form_records_round_trip_and_v1_still_imports():
    # #262: v2 adds the hand.equity A/B log; a v1 text (no eqab) must still import.
    rec = [{"f": "A", "ms": 2310, "a": 2, "t": 3, "seed": 7}, {"f": "B", "ms": 980, "a": 0, "t": 0, "seed": 7}]
    v2 = {"schema": "stalker.demo.records", "schema_version": 2, "weak": {}, "itimes": [], "rankq": {"n": 0, "sum": 0}, "eqab": rec}
    v1 = {"schema": "stalker.demo.records", "schema_version": 1, "itimes": [3.0]}
    bad = [dict(v2, eqab=[dict(rec[0], f="C")]), dict(v2, eqab=[dict(rec[0], a=5)]), dict(v2, eqab=[dict(rec[0], ms=-1)]), dict(v2, eqab={})]
    res = _parse([json.dumps(v2), json.dumps(v1)] + [json.dumps(b) for b in bad])
    assert res[0]["data"]["eqab"] == rec
    assert res[1]["data"]["eqab"] == [] and res[1]["data"]["itimes"] == [3.0]
    assert all("eqab" in r["error"] and "그대로 붙여넣으세요" in r["error"] for r in res[2:])


def test_demo_records_version_is_2():
    assert re.search(r'RECORDS_VERSION = 2;', DEMO)
