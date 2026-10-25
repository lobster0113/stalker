"""Build `service/web/data/` for the learning page (see service/web/README.md).

`report.json` is the typing report after a schema check (a v1 report is upgraded first: v1 never judged S4/S5,
so none of its cells is lessonable); `quiz.json` holds quiz spots cut from decision records of lessonable cells
only (charter 5: insufficient types are not taught). A spot carries only what the player may see (public table
state, own hole cards, legal actions) plus the AI's mixed strategy; the stable id and the cell label let the page
link a spot to its cell.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import numpy as np

from stalker.records.schema import DecisionRecord
from stalker.records.store import iter_records
from stalker.typing.report import REPORT_SCHEMA_VERSION
from stalker.typing.spots import ACTION_CATEGORIES, spot_key

QUIZ_SCHEMA_VERSION = 1
DEFAULT_MAX_SPOTS = 60


def upgrade_report(report: dict) -> dict:
    """Return `report` in the current schema. v1 cells carried only S1 (`s1_pass`), so they become not lessonable."""
    if report.get("schema_version") != 1:
        return report
    r = copy.deepcopy(report)
    for c in r.get("cells", []):
        c.update(s1=bool(c.pop("s1_pass", False)), s4=False, s5=False, lessonable=False)
    summary = r.setdefault("summary", {})
    summary.update(lessonable_cells=0, d1_preliminary={"lessonable_decision_share": 0.0,
                                                        "note": "v1 report: S4/S5 were not judged"})
    r["schema_version"] = REPORT_SCHEMA_VERSION
    return r


def validate_report(report: dict) -> list[str]:
    """Problems that would break the page; empty list = ok."""
    e: list[str] = []
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        e.append(f"report schema_version must be {REPORT_SCHEMA_VERSION}, got {report.get('schema_version')!r}; rebuild the report")
    if "lessonable_cells" not in report.get("summary", {}):
        e.append("report.summary.lessonable_cells missing")
    cells = report.get("cells")
    if not isinstance(cells, list):
        return e + ["report.cells must be a list"]
    for i, c in enumerate(cells):
        where = f"cells[{i}]"
        for k in ("label", "n_decisions", "n_games", "s1", "s4", "s5", "lessonable", "status", "actions"):
            if k not in c:
                e.append(f"{where}.{k} missing")
        for a in ACTION_CATEGORIES:
            if a not in c.get("actions", {}) or "mean" not in c["actions"][a]:
                e.append(f"{where}.actions.{a}.mean missing")
    return e


def validate_quiz(quiz: dict) -> list[str]:
    e: list[str] = []
    if quiz.get("schema_version") != QUIZ_SCHEMA_VERSION:
        e.append(f"quiz schema_version must be {QUIZ_SCHEMA_VERSION}")
    spots = quiz.get("spots")
    if not isinstance(spots, list):
        return e + ["quiz.spots must be a list"]
    for s in spots:
        where = f"spot {s.get('id')!r}"
        opts, probs = s.get("options", []), s.get("probs", [])
        if not opts or len(opts) != len(probs):
            e.append(f"{where}: options and probs must be the same non-zero length")
        elif abs(sum(probs) - 1.0) > 1e-6:
            e.append(f"{where}: probs must sum to 1")
        if s.get("values") is not None and len(s["values"]) != len(opts):
            e.append(f"{where}: values must align with options")
        for k in ("id", "cell", "street", "hole_cards", "board", "pot", "bb", "hero", "seats"):
            if k not in s:
                e.append(f"{where}: {k} missing")
    return e


def _spot(r: DecisionRecord, players: int | None) -> dict | None:
    key = spot_key(r, players)
    if key is None:
        return None
    ob, tc = r.table_observation, r.tournament_context
    legal = [i for i, ok in enumerate(ob.legal_action_mask) if ok]
    total = sum(r.probs_ai0[i] for i in legal)
    if not legal or total <= 0:
        return None
    return {
        "id": f"{r.ids.game_id}:{r.ids.hand_id}:{r.ids.decision_id}",
        "cell": key.label(),
        "street": ob.street,
        "position": ob.position,
        "hole_cards": list(ob.hole_cards),
        "board": list(ob.board),
        "pot": ob.pot,
        "bb": tc.bb,
        "hero": ob.hero_seat,
        "seats": [{"seat": s.seat, "stack": s.stack, "bet": s.bet, "in_hand": s.in_hand} for s in ob.seats],
        "options": [{"kind": ob.action_space[i].kind, "amount": ob.action_space[i].amount} for i in legal],
        "probs": [r.probs_ai0[i] / total for i in legal],
        "values": [r.action_values[i] for i in legal] if r.action_values is not None else None,
    }


def build_quiz(run_dir: str | Path, lessonable_cells: set[str], *, max_spots: int = DEFAULT_MAX_SPOTS, seed: int = 0,
               players: int | None = None) -> dict:
    """Pick up to `max_spots` decisions with a real choice (>= 2 legal actions) from `lessonable_cells`, by seeded sampling."""
    spots = [s for r in iter_records(run_dir) if isinstance(r, DecisionRecord)
             if sum(r.table_observation.legal_action_mask) >= 2
             if (s := _spot(r, players)) is not None and s["cell"] in lessonable_cells]
    rng = np.random.default_rng(seed)
    if len(spots) > max_spots:
        idx = sorted(rng.choice(len(spots), size=max_spots, replace=False))
        spots = [spots[i] for i in idx]
    return {"schema_version": QUIZ_SCHEMA_VERSION, "spots": spots}


def build(run_dir: str | Path, out_dir: str | Path, *, max_spots: int = DEFAULT_MAX_SPOTS, seed: int = 0) -> tuple[Path, Path]:
    run, out = Path(run_dir), Path(out_dir)
    report = upgrade_report(json.loads((run / "report.json").read_text(encoding="utf-8")))
    problems = validate_report(report)
    lessonable = {c["label"] for c in report.get("cells", []) if c.get("lessonable")}
    quiz = build_quiz(run, lessonable, max_spots=max_spots, seed=seed, players=None)
    problems += validate_quiz(quiz)
    if problems:
        raise ValueError("learning-page data invalid:\n  " + "\n  ".join(problems))
    out.mkdir(parents=True, exist_ok=True)
    rp, qp = out / "report.json", out / "quiz.json"
    rp.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    qp.write_text(json.dumps(quiz, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return rp, qp


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", help="output of stalker.pipeline.generate (records.jsonl + report.json)")
    ap.add_argument("--out", default="service/web/data")
    ap.add_argument("--max-spots", type=int, default=DEFAULT_MAX_SPOTS)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    rp, qp = build(a.run_dir, a.out, max_spots=a.max_spots, seed=a.seed)
    print(f"{rp}, {qp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
