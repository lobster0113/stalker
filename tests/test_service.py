import copy
import dataclasses
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from stalker.pipeline.generate import main as generate_main
from stalker.records.schema import DecisionRecord
from stalker.records.store import iter_records
from stalker.service.build import _spot, build, upgrade_report, validate_quiz, validate_report

WEB = Path(__file__).resolve().parent.parent / "service" / "web"


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("run")
    generate_main(["--preset", "sng6", "--n", "2", "--seed", "3", "--out", str(d)])
    return d


@pytest.fixture
def lessonable_run(run_dir, tmp_path):
    """run_dir with every cell marked lessonable (2 games are far too few for real verdicts)."""
    d = tmp_path / "lessonable_run"
    shutil.copytree(run_dir, d)
    report = json.loads((d / "report.json").read_text(encoding="utf-8"))
    for c in report["cells"]:
        c.update(s1=True, s4=True, s5=True, lessonable=True)
    (d / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return d


def _v1(report: dict) -> dict:
    """The schema v1 shape of a report (before referee.sufficiency): S1 only, no S4/S5/lessonable."""
    old = copy.deepcopy(report)
    old["schema_version"] = 1
    old["summary"] = {"cells": len(old["cells"]), "s1_pass_cells": 0, "s1_pass_decision_share": 0.0}
    for c in old["cells"]:
        c["s1_pass"] = c.pop("s1")
        for k in ("s4", "s5", "lessonable", "n_games_ab"):
            c.pop(k)
    return old


def test_build_outputs_validate_and_are_deterministic(lessonable_run, tmp_path):
    run_dir = lessonable_run
    rp, qp = build(run_dir, tmp_path / "a", max_spots=10, seed=1)
    report, quiz = json.loads(rp.read_text(encoding="utf-8")), json.loads(qp.read_text(encoding="utf-8"))
    assert validate_report(report) == [] and validate_quiz(quiz) == []
    assert 0 < len(quiz["spots"]) <= 10
    _, qp2 = build(run_dir, tmp_path / "b", max_spots=10, seed=1)
    assert qp.read_text(encoding="utf-8") == qp2.read_text(encoding="utf-8")
    labels = {c["label"] for c in report["cells"]}
    assert all(s["cell"] in labels for s in quiz["spots"])


def test_quiz_takes_spots_only_from_lessonable_cells(run_dir, lessonable_run, tmp_path):
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["lessonable_cells"] == 0  # 2 games: nothing is sufficient
    _, qp = build(run_dir, tmp_path / "none", max_spots=50)
    assert json.loads(qp.read_text(encoding="utf-8"))["spots"] == []
    some = json.loads((lessonable_run / "report.json").read_text(encoding="utf-8"))
    keep = {c["label"] for c in some["cells"][::2]}
    for c in some["cells"]:
        c["lessonable"] = c["label"] in keep
    (lessonable_run / "report.json").write_text(json.dumps(some), encoding="utf-8")
    _, qp = build(lessonable_run, tmp_path / "some", max_spots=500)
    spots = json.loads(qp.read_text(encoding="utf-8"))["spots"]
    assert spots and {s["cell"] for s in spots} <= keep


def test_v1_report_still_builds_with_nothing_lessonable(run_dir, tmp_path):
    v1_run = tmp_path / "v1_run"
    shutil.copytree(run_dir, v1_run)
    v1 = _v1(json.loads((run_dir / "report.json").read_text(encoding="utf-8")))
    (v1_run / "report.json").write_text(json.dumps(v1), encoding="utf-8")
    rp, qp = build(v1_run, tmp_path / "out", max_spots=50)
    out = json.loads(rp.read_text(encoding="utf-8"))
    assert validate_report(out) == [] and out["schema_version"] == 3
    assert out["summary"]["lessonable_cells"] == 0 and not any(c["lessonable"] for c in out["cells"])
    assert json.loads(qp.read_text(encoding="utf-8"))["spots"] == []
    assert upgrade_report(out) == out  # current-schema reports pass through unchanged


def _v2(report: dict, n_games_ab: list[int]) -> dict:
    """The schema v2 shape: S1 without the rule-of-three floor, plus the report-side zero-variance guard."""
    old = copy.deepcopy(report)
    old["schema_version"] = 2
    old["criteria"]["zero_variance_min_games"] = 60
    for c in old["cells"]:
        c.update(s1=True, s4=True, s5=True, lessonable=True, zero_variance_guard=False, n_games_ab=n_games_ab)
        c["actions"]["fold"].update(main=True, half_width=0.0, ess=None, ess_note="zero variance on a half")
        c["actions"]["call"].update(main=True, half_width=0.04, ess=150.0)
    return old


@pytest.mark.parametrize("n_games_ab,ok", [([59, 80], False), ([60, 61], True)])
def test_v2_report_gets_rule_of_three_floor(run_dir, n_games_ab, ok):
    """A v2 S1 pass survives only with >= ceil(3 / 0.05) = 60 games on each half."""
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    out = upgrade_report(_v2(report, n_games_ab))
    assert validate_report(out) == [] and out["schema_version"] == 3
    assert "zero_variance_min_games" not in out["criteria"]
    n = min(n_games_ab)
    for c in out["cells"]:
        assert "zero_variance_guard" not in c and (c["s1"], c["lessonable"]) == (ok, ok)
        fold, call = c["actions"]["fold"], c["actions"]["call"]
        assert fold["ess"] == n and "ess_note" not in fold and fold["half_width"] == pytest.approx(3 / n)
        assert call["half_width"] == pytest.approx(max(0.04, 3 / n))
    assert out["summary"]["lessonable_cells"] == (len(out["cells"]) if ok else 0)
    assert out["summary"]["d1_preliminary"]["lessonable_decision_share"] == (1.0 if ok else 0.0)


def test_quiz_spots_expose_no_hidden_cards(lessonable_run, tmp_path):
    _, qp = build(lessonable_run, tmp_path, max_spots=50)
    card = re.compile(r"[2-9TJQKA][cdhs]")
    spots = json.loads(qp.read_text(encoding="utf-8"))["spots"]
    assert spots
    for s in spots:
        assert len(s["hole_cards"]) == 2 and set(s) >= {"id", "cell", "options", "probs"}
        assert len(s["options"]) >= 2
        # id / cell label are free of card-like tokens only by construction; check the card-bearing fields
        shown = set(s["hole_cards"]) | set(s["board"])
        assert set(card.findall(json.dumps({k: v for k, v in s.items() if k not in ("id", "cell")}))) <= shown
        assert not set(s) & {"chosen_action", "probs_ai1", "acting_policy", "opponent_hole_cards", "hole_cards_opp"}


def test_quiz_values_follow_legal_actions(run_dir):
    recs = [r for r in iter_records(run_dir) if isinstance(r, DecisionRecord) and sum(r.table_observation.legal_action_mask) >= 2]
    r = recs[0]
    n = len(r.table_observation.action_space)
    vals = tuple(float(i) * 10 + 1 for i in range(n))
    spot = _spot(dataclasses.replace(r, action_values=vals), None)
    legal = [i for i, ok in enumerate(r.table_observation.legal_action_mask) if ok]
    assert spot is not None and len(spot["values"]) == len(spot["options"]) == len(legal)
    assert spot["values"] == [vals[i] for i in legal]


def test_validators_report_fixable_problems():
    assert any("schema_version" in e for e in validate_report({"schema_version": 99, "cells": []}))
    quiz = {"schema_version": 1, "spots": [{"id": "x", "options": [{}], "probs": [0.5]}]}
    assert any("sum to 1" in e for e in validate_quiz(quiz))


def test_committed_sample_data_is_valid():
    report = json.loads((WEB / "data" / "report.json").read_text(encoding="utf-8"))
    quiz = json.loads((WEB / "data" / "quiz.json").read_text(encoding="utf-8"))
    assert validate_report(report) == [] and validate_quiz(quiz) == []
    lessonable = {c["label"] for c in report["cells"] if c["lessonable"]}
    assert all(s["cell"] in lessonable for s in quiz["spots"])


def test_page_badge_shows_insufficient_unless_lessonable():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed; the badge logic in app.js is plain JS")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    fn = re.search(r"^function cellBadge\(c\) \{.*?^\}", js, re.S | re.M).group(0)
    cells = [{"lessonable": True, "s1": True, "s4": True, "s5": True},
             {"lessonable": False, "s1": True, "s4": True, "s5": False, "status": "ok"},
             {"s1_pass": True, "status": "ok"}]  # a cell without the field is never taught
    out = subprocess.run([node, "-e", fn + f"\nfor (const c of {json.dumps(cells)}) console.log(cellBadge(c));"],
                         capture_output=True, text=True, check=True, encoding="utf-8").stdout.splitlines()
    assert "교훈 가능" in out[0] and "표본 부족" not in out[0]
    assert all("표본 부족" in o and "교훈 가능" not in o for o in out[1:])
    assert "S5 ✗" in out[1]
    assert "s1_pass" not in js


def test_html_has_required_elements():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<meta name="viewport" content="[^"]*width=device-width', html)
    for ident in ("view-types", "view-quiz", "types-table", "quiz-options", "quiz-result"):
        assert f'id="{ident}"' in html
    assert "app.js" in html and "style.css" in html


def test_no_external_dependencies_except_cdnjs():
    for f in ("index.html", "style.css", "app.js"):
        urls = re.findall(r"https?://[^\s\"')]+", (WEB / f).read_text(encoding="utf-8"))
        assert all(u.startswith("https://cdnjs.cloudflare.com/") for u in urls), (f, urls)


def test_css_supports_dark_mode_and_no_fixed_wide_layout():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "prefers-color-scheme: dark" in css
    assert not re.search(r"(?<!max-)(?<!min-)width:\s*(\d{4,})px", css)
