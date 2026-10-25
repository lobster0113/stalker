"""Typing report: per-cell decision counts, action frequencies and the referee's S1/S4/S5 verdicts.

Frequencies are the mean of the AI's mixed-strategy probabilities (`probs_ai0`) per action category.
Sufficiency is judged only by `referee.sufficiency.judge_cell` (referee/DATA_SUFFICIENCY.md §1). S4 needs two
independently seeded datasets, so each cell's games are split by order of first appearance into even and odd
halves: `stalker.pipeline.generate` seeds game i with `[seed, i]`, so the halves come from disjoint seed sets.
Both halves are judged (`judge_cell(A, B)` and `judge_cell(B, A)`); a cell is `lessonable` only if S1 and S5 hold
on both halves and S4 holds between them. Per-action half-width/ESS are the worse of the two halves.
The referee's S1 floors every half-width by the rule of three (3 / games on that half), so no extra guard here.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from referee.sufficiency import Verdict, judge_cell, make_cell
from stalker.records.schema import DecisionRecord
from stalker.typing.spots import ACTION_CATEGORIES, category_probs, spot_key

REPORT_SCHEMA_VERSION = 3


@dataclass(frozen=True)
class _Obs:
    game_id: str
    probs: dict[str, float]


def build_report(decisions: Iterable[DecisionRecord], *, players: int | None = None, seed: int = 0,
                 source: dict | None = None) -> dict:
    cells: dict[str, list[_Obs]] = defaultdict(list)
    keys = {}
    game_order: dict[str, int] = {}
    total = unclassified = 0
    for r in decisions:
        total += 1
        game_order.setdefault(r.ids.game_id, len(game_order))
        key = spot_key(r, players)
        if key is None:
            unclassified += 1
            continue
        keys[key.label()] = key
        cells[key.label()].append(_Obs(r.ids.game_id, category_probs(r)))
    out_cells = [_cell(label, keys[label], cells[label], game_order, seed, i) for i, label in enumerate(sorted(cells))]
    classified = total - unclassified
    lessonable = [c for c in out_cells if c["lessonable"]]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "source": source or {},
        "criteria": {"judge": "referee.sufficiency.judge_cell", "lessonable": "S1 and S4 and S5",
                     "split": "games by first-appearance order: even -> A, odd -> B", "cluster": "game_id", "seed": seed},
        "decisions": total,
        "unclassified": {"count": unclassified, "ratio": unclassified / total if total else 0.0},
        "summary": {
            "cells": len(out_cells),
            "lessonable_cells": len(lessonable),
            "d1_preliminary": {
                "lessonable_decision_share": sum(c["n_decisions"] for c in lessonable) / classified if classified else 0.0,
                "note": "예비: 이 데이터의 결정 빈도로 가중. 실전 출현 빈도가 아니므로 D1 판정이 아니다.",
            },
        },
        "cells": out_cells,
    }


def _side_seed(seed: int, cell_index: int, side: int) -> int:
    return int(np.random.SeedSequence([seed, cell_index, side]).generate_state(1)[0])


def _cell(label: str, key, obs: list[_Obs], game_order: dict[str, int], seed: int, index: int) -> dict:
    halves: tuple[list[_Obs], list[_Obs]] = ([], [])
    for o in obs:
        halves[game_order[o.game_id] % 2].append(o)
    probs = np.array([[o.probs[a] for a in ACTION_CATEGORIES] for o in obs])
    means = probs.mean(axis=0)
    cell = {"label": label, "key": key.__dict__.copy(), "n_decisions": len(obs), "n_games": len({o.game_id for o in obs}),
            "n_games_ab": [len({o.game_id for o in h}) for h in halves],
            "actions": {a: {"mean": float(m)} for a, m in zip(ACTION_CATEGORIES, means)},
            "s1": False, "s4": False, "s5": False, "lessonable": False, "status": "ok"}
    if min(cell["n_games_ab"]) < 2:
        # S1 needs two tournaments on each half, so it cannot pass; skip the referee call.
        cell["status"] = "insufficient_games"
        if not all(halves):
            return cell
    a, b = (make_cell([[o.probs[x] for x in ACTION_CATEGORIES] for o in h], [o.game_id for o in h]) for h in halves)
    va, vb = judge_cell(a, b, seed=_side_seed(seed, index, 0)), judge_cell(b, a, seed=_side_seed(seed, index, 1))
    cell.update(s1=va.s1.passed and vb.s1.passed, s4=va.s4, s5=va.s5 and vb.s5)
    cell["lessonable"] = cell["s1"] and cell["s4"] and cell["s5"]
    _precision(cell, (va, vb))
    return cell


def _precision(cell: dict, verdicts: tuple[Verdict, Verdict]) -> None:
    worst: dict[int, tuple[float, float]] = {}
    for v in verdicts:
        for p in v.s1.actions:
            hw, ess = worst.get(p.action, (0.0, float("inf")))
            worst[p.action] = (max(hw, p.half_width), min(ess, p.ess))
    for i, (hw, ess) in sorted(worst.items()):
        entry = cell["actions"][ACTION_CATEGORIES[i]]
        entry.update(main=True, half_width=hw, ess=ess)


def to_markdown(report: dict, top: int = 40) -> str:
    s, u = report["summary"], report["unclassified"]
    lines = [
        "# Typing report v0", "",
        f"- decisions: {report['decisions']} (unclassified: {u['count']}, {u['ratio']:.1%})",
        f"- cells: {s['cells']}, lessonable (S1·S4·S5, `referee.sufficiency`): {s['lessonable_cells']}",
        f"- D1 예비값 (이 데이터의 결정 빈도 가중, 판정 아님): {s['d1_preliminary']['lessonable_decision_share']:.1%}",
        f"- S4 split: {report['criteria']['split']}; CI clusters = {report['criteria']['cluster']}",
        *([f"- source: {json.dumps(report['source'], ensure_ascii=False)}"] if report["source"] else []), "",
        f"## Largest {top} cells", "",
        "| cell (stage/stack bb/pos/street/pot/opp) | decisions | games (A/B) | " + " | ".join(
            f"{a} (±hw, ESS)" for a in ACTION_CATEGORIES) + " | S1 | S4 | S5 | 교훈 |",
        "|---|---|---|" + "---|" * len(ACTION_CATEGORIES) + "---|---|---|---|",
    ]
    mark = {True: "✓", False: "✗"}
    for c in sorted(report["cells"], key=lambda c: -c["n_decisions"])[:top]:
        cols = []
        for a in ACTION_CATEGORIES:
            x = c["actions"][a]
            if "half_width" not in x:
                cols.append(f"{x['mean']:.2f}")
                continue
            cols.append(f"{x['mean']:.2f} (±{x['half_width']:.2f}, {x['ess']:.0f})")
        verdict = "가능" if c["lessonable"] else "표본 부족"
        ga, gb = c["n_games_ab"]
        lines.append(f"| {c['label']} | {c['n_decisions']} | {c['n_games']} ({ga}/{gb}) | " + " | ".join(cols)
                     + f" | {mark[c['s1']]} | {mark[c['s4']]} | {mark[c['s5']]} | {verdict} |")
    return "\n".join(lines) + "\n"


def write_report(report: dict, out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    j, m = out / "report.json", out / "report.md"
    j.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    m.write_text(to_markdown(report), encoding="utf-8")
    return j, m
