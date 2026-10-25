import copy
import dataclasses
import json
import re
from pathlib import Path

import pytest

from stalker.pipeline.generate import main as generate_main
from stalker.records.schema import DecisionRecord
from stalker.records.store import iter_records
from stalker.service.build import _spot, build, validate_quiz, validate_report

WEB = Path(__file__).resolve().parent.parent / "service" / "web"


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("run")
    generate_main(["--preset", "sng6", "--n", "2", "--seed", "3", "--out", str(d)])
    return d


def test_build_outputs_validate_and_are_deterministic(run_dir, tmp_path):
    rp, qp = build(run_dir, tmp_path / "a", max_spots=10, seed=1)
    report, quiz = json.loads(rp.read_text()), json.loads(qp.read_text())
    assert validate_report(report) == [] and validate_quiz(quiz) == []
    assert 0 < len(quiz["spots"]) <= 10
    _, qp2 = build(run_dir, tmp_path / "b", max_spots=10, seed=1)
    assert qp.read_text() == qp2.read_text()
    labels = {c["label"] for c in report["cells"]}
    assert all(s["cell"] in labels for s in quiz["spots"])


def test_quiz_spots_expose_no_hidden_cards(run_dir, tmp_path):
    _, qp = build(run_dir, tmp_path, max_spots=50)
    card = re.compile(r"[2-9TJQKA][cdhs]")
    spots = json.loads(qp.read_text())["spots"]
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
    report = json.loads((WEB / "data" / "report.json").read_text())
    quiz = json.loads((WEB / "data" / "quiz.json").read_text())
    assert validate_report(report) == [] and validate_quiz(quiz) == []
    bad = copy.deepcopy(quiz)
    bad["spots"][0]["probs"] = [1.0]
    assert validate_quiz(bad)


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
