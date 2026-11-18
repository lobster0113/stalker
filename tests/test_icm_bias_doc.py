"""The ICM bias report (#845) must match the JSON it says it was made from: same cell count, schema and numbers."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs/research/2026-11-icm-bias-measurement.md"
DATA = {"random": "icm-bias-2026-11-13-random.json", "persona:tag": "icm-bias-2026-11-13-tag.json"}


def _table_rows(agents: str) -> list[list[str]]:
    lines = DOC.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"### 결과: {agents}") + 1
    rows = []
    for ln in lines[start:]:
        if ln.startswith("#"):
            break
        if ln.startswith("| ") and not ln.startswith("| preset"):
            rows.append([c.strip() for c in ln.strip("|").split(" | ")])
    return rows


@pytest.mark.parametrize("agents", sorted(DATA))
def test_doc_table_matches_committed_json(agents):
    d = json.loads((ROOT / "docs/research/data" / DATA[agents]).read_text(encoding="utf-8"))
    assert d["schema_version"] == 1
    assert d.get("agents", "random") == agents
    assert d["skipped"] == []
    rows = _table_rows(agents)
    assert len(rows) == len(d["cells"]) == 27, "regenerate the table with the command in the doc"
    for row, c in zip(rows, d["cells"]):
        assert row == [c["preset"], str(c["remaining"]), c["profile"], f"{c['max_abs_diff_rel']:.4f}",
                       f"{c['max_abs_z']:.2f}"]
