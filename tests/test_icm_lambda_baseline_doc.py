"""The λ baseline (#870) must agree with the tool's own ADR 0026 rule: re-summarising the committed cells and calling
select_lambda again gives the committed selected_lambda, and the report quotes those values."""
import json
from pathlib import Path

import pytest

from stalker.tools.icm_grid import select_lambda, summarize_lambdas

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs/research/2026-11-icm-lambda-baseline.md"
DATA = {"random": "icm-lambda-2026-11-14-random.json", "persona:tag": "icm-lambda-2026-11-14-tag.json"}


@pytest.mark.parametrize("agents", sorted(DATA))
def test_selected_lambda_follows_adr_0026_rule(agents):
    d = json.loads((ROOT / "docs/research/data" / DATA[agents]).read_text(encoding="utf-8"))
    assert d["schema_version"] == 3 and d.get("agents", "random") == agents and d["skipped"] == []
    assert len(d["cells"]) == 2 * 3 * 3 * 3, "regenerate with the command in the baseline doc"
    summary = summarize_lambdas(d["cells"], d["lambda_grid"])
    assert summary == d["lambda_summary"], "lambda_summary does not match its cells; rerun icm_grid"
    assert select_lambda(summary) == d["selected_lambda"]
    assert f"| {agents} | {d['selected_lambda']} |" in DOC.read_text(encoding="utf-8"), "update the doc's λ table"
