"""The levels/layouts report (#858) must match the JSON it was made from: cell counts, level/layout fields, numbers."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs/research/2026-11-icm-bias-levels-layouts.md"
DATA = {"random": "icm-bias-levels-2026-11-14-random.json", "persona:tag": "icm-bias-levels-2026-11-14-tag.json"}
HEADING = {"random": "### 결과: random", "persona:tag": "### 결과: persona:tag"}


def _rows(agents: str) -> list[list[str]]:
    lines = DOC.read_text(encoding="utf-8").splitlines()
    rows = []
    for ln in lines[lines.index(HEADING[agents]) + 1:]:
        if ln.startswith("#"):
            break
        if ln.startswith("| ") and not ln.startswith("| preset"):
            rows.append([c.strip() for c in ln.strip("|").split(" | ")])
    return rows


@pytest.mark.parametrize("agents", sorted(DATA))
def test_doc_table_matches_committed_json(agents):
    d = json.loads((ROOT / "docs/research/data" / DATA[agents]).read_text(encoding="utf-8"))
    assert d["schema_version"] == 2 and d.get("agents", "random") == agents
    assert d["level_indexes"] == [0, 6] and d["layouts"] == 3 and d["games"] == 1000 and d["skipped"] == []
    rows = _rows(agents)
    assert len(rows) == len(d["cells"]) == 2 * 1 * 3 * 2 * 3, "regenerate the table with the command in the doc"
    assert {(c["level_index"], c["layout"]) for c in d["cells"]} == {(lv, k) for lv in (0, 6) for k in range(3)}
    for row, c in zip(rows, d["cells"]):
        assert row == [c["preset"], str(c["remaining"]), c["profile"], str(c["level_index"]), str(c["layout"]),
                       f"{c['max_abs_diff_rel']:.4f}", f"{c['max_abs_z']:.2f}"]


def test_layouts_of_a_cell_use_different_stacks():
    d = json.loads((ROOT / "docs/research/data" / DATA["random"]).read_text(encoding="utf-8"))
    by = {}
    for c in d["cells"]:
        if c["profile"] != "even":
            by.setdefault((c["preset"], c["profile"], c["level_index"]), []).append(tuple(c["calibrate"]["stacks"]))
    assert all(len(set(v)) == 3 for v in by.values())
