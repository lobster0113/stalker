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
    newer = dict(good, schema_version=2)
    bad_weak = dict(good, weak={"hand.equity": {"n": "x"}})
    res = _parse([json.dumps(good), "{oops", json.dumps({"schema": "other"}), json.dumps(newer), json.dumps(bad_weak),
                  json.dumps(dict(good, itimes=[-1]))])
    assert res[0]["data"]["weak"] == good["weak"] and res[0]["data"]["itimes"] == [4.2, 7.0]
    assert "그대로 붙여넣으세요" in res[1]["error"]
    assert "schema" in res[2]["error"]
    assert "새로 고친 뒤" in res[3]["error"]
    assert "weak" in res[4]["error"] and "itimes" in res[5]["error"]


def test_missing_fields_default_to_empty_records():
    (r,) = _parse([json.dumps({"schema": "stalker.demo.records", "schema_version": 1})])
    assert r["data"] == {"weak": {}, "itimes": [], "rankq": {"n": 0, "sum": 0}}
