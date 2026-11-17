"""#935: the same-seed CI baselines in the F7a doc must agree with their committed result copies: the cells share the
policy run's stacks, re-summarising the cells and calling select_lambda gives each run's selected_lambda, and the doc
quotes those values."""
import json
from pathlib import Path

import pytest

from stalker.tools.icm_grid import select_lambda, summarize_lambdas

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs/research/2026-11-e-f7-lambda-policy.md"
DATA = ROOT / "docs/research/data"
RUNS = {"policy": "43778587487", "random": "44044054460", "tag": "44045077233"}


def _grid(agent):
    d = json.loads((DATA / f"icm-lambda-f7-ci-{agent}-{RUNS[agent]}.json").read_text(encoding="utf-8"))
    assert d["schema"] == "stalker.icm.lambda-grid-pair" and list(d["agents"]) == [agent]
    return d["agents"][agent]


@pytest.mark.parametrize("agent", sorted(RUNS))
def test_selected_lambda_recomputes_from_copy(agent):
    g = _grid(agent)
    assert g["schema_version"] == 3 and g["seed"] == 10001 and g["games"] == 1000 and g["skipped"] == []
    assert len(g["cells"]) == 9, "copy the full ops:cloud/results/<run>.json"
    summary = summarize_lambdas(g["cells"], g["lambda_grid"])
    assert summary == g["lambda_summary"], "lambda_summary does not match its cells; recopy the result"
    assert select_lambda(summary) == g["selected_lambda"]


def test_baselines_share_policy_cells_and_doc_quotes_them():
    grids = {a: _grid(a) for a in RUNS}
    key = lambda c: (c["preset"], c["remaining"], c["profile"], c["layout"], tuple(c["calibrate"]["stacks"]))
    policy_cells = [key(c) for c in grids["policy"]["cells"]]
    for a in ("random", "tag"):
        assert [key(c) for c in grids[a]["cells"]] == policy_cells, f"{a}: cells differ from the policy run (seed?)"
    text = DOC.read_text(encoding="utf-8")
    row = "| **채택 λ** | **" + "** | **".join(f"{grids[a]['selected_lambda']:g}" for a in RUNS) + "** |"
    assert row in text, "update the doc's same-seed λ summary row"
    for a, run in RUNS.items():
        assert run in text
