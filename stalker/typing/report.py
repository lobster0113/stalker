"""Typing report: per-cell decision counts, action frequencies with clustered 95% CIs, ESS and the S1 verdict.

Frequencies are the mean of the AI's mixed-strategy probabilities (`probs_ai0`) per action category. Decisions of
one game are correlated, so the CI resamples whole games (`referee.stats.bootstrap_ci`); ESS = p(1-p)/Var(p_hat).
S1 (referee/DATA_SUFFICIENCY.md): every main action (mean >= MAIN_ACTION_MIN) has CI half-width <= S1_HALF_WIDTH.
Zero-variance cells (every probability identical) would get half-width 0 from the bootstrap, so they use the
rule-of-three bound 3/n_games instead, and any cell needs MIN_GAMES independent games before S1 can pass.
Only S1 is evaluated here; S4/S5 come from `referee.sufficiency` once it replaces this in a follow-up.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from referee.stats import bootstrap_ci
from stalker.records.schema import DecisionRecord
from stalker.typing.spots import ACTION_CATEGORIES, category_probs, spot_key

REPORT_SCHEMA_VERSION = 1
S1_HALF_WIDTH = 0.05
MAIN_ACTION_MIN = 0.05
MIN_GAMES = 30
Z95 = 1.959964
N_BOOT = 1000


@dataclass(frozen=True)
class _Obs:
    game_id: str
    probs: dict[str, float]


def build_report(decisions: Iterable[DecisionRecord], *, players: int | None = None, seed: int = 0,
                 n_boot: int = N_BOOT, source: dict | None = None) -> dict:
    cells: dict[str, list[_Obs]] = defaultdict(list)
    keys = {}
    total = unclassified = 0
    for r in decisions:
        total += 1
        key = spot_key(r, players)
        if key is None:
            unclassified += 1
            continue
        keys[key.label()] = key
        cells[key.label()].append(_Obs(r.ids.game_id, category_probs(r)))
    out_cells = []
    for i, label in enumerate(sorted(cells)):
        out_cells.append(_cell(label, keys[label], cells[label], np.random.default_rng([seed, i]), n_boot))
    classified = total - unclassified
    passing = [c for c in out_cells if c["s1_pass"]]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "source": source or {},
        "criteria": {"s1_half_width": S1_HALF_WIDTH, "main_action_min": MAIN_ACTION_MIN, "min_games": MIN_GAMES, "ci_level": 0.95,
                     "cluster": "game_id", "n_boot": n_boot, "seed": seed},
        "decisions": total,
        "unclassified": {"count": unclassified, "ratio": unclassified / total if total else 0.0},
        "summary": {
            "cells": len(out_cells),
            "s1_pass_cells": len(passing),
            "s1_pass_decision_share": sum(c["n_decisions"] for c in passing) / classified if classified else 0.0,
        },
        "cells": out_cells,
    }


def _cell(label: str, key, obs: list[_Obs], rng: np.random.Generator, n_boot: int) -> dict:
    games = {o.game_id for o in obs}
    cell = {"label": label, "key": key.__dict__.copy(), "n_decisions": len(obs), "n_games": len(games),
            "actions": {}, "s1_pass": False, "status": "ok"}
    means = {a: float(np.mean([o.probs[a] for o in obs])) for a in ACTION_CATEGORIES}
    if len(games) < 2 or len(obs) < 2:
        cell["status"] = "insufficient_games"
        cell["actions"] = {a: {"mean": m} for a, m in means.items()}
        return cell
    ids = [o.game_id for o in obs]
    main_ok = []
    for a in ACTION_CATEGORIES:
        ci = bootstrap_ci([o.probs[a] for o in obs], ids, n_boot=n_boot, rng=rng)
        half = (ci.hi - ci.lo) / 2
        p = ci.mean
        entry = {"mean": p, "lo": ci.lo, "hi": ci.hi, "half_width": half}
        if half > 1e-12:
            entry["ess"] = p * (1 - p) / (half / Z95) ** 2 if 0 < p < 1 else None
        else:
            # Bootstrap spread of a constant is 0, which is not precision: bound it by the games seen.
            half = max(half, 3.0 / len(games))
            entry.update(half_width=half, ess=None, ess_note="zero variance; half-width is the 3/n_games bound")
        cell["actions"][a] = entry
        if p >= MAIN_ACTION_MIN:
            cell["actions"][a]["main"] = True
            main_ok.append(half <= S1_HALF_WIDTH)
    cell["s1_pass"] = bool(main_ok) and all(main_ok) and len(games) >= MIN_GAMES
    return cell


def to_markdown(report: dict, top: int = 40) -> str:
    s, u = report["summary"], report["unclassified"]
    lines = [
        "# Typing report v0", "",
        f"- decisions: {report['decisions']} (unclassified: {u['count']}, {u['ratio']:.1%})",
        f"- cells: {s['cells']}, S1 pass: {s['s1_pass_cells']} "
        f"(share of classified decisions: {s['s1_pass_decision_share']:.1%})",
        f"- S1: every main action (mean >= {report['criteria']['main_action_min']:.0%}) has 95% CI half-width "
        f"<= {report['criteria']['s1_half_width']:.0%}p; CI clusters = {report['criteria']['cluster']}",
        *([f"- source: {json.dumps(report['source'], ensure_ascii=False)}"] if report["source"] else []), "",
        f"## Largest {top} cells", "",
        "| cell (stage/stack bb/pos/street/pot/opp) | decisions | games | " + " | ".join(
            f"{a} (±hw, ESS)" for a in ACTION_CATEGORIES) + " | S1 |",
        "|---|---|---|" + "---|" * len(ACTION_CATEGORIES) + "---|",
    ]
    for c in sorted(report["cells"], key=lambda c: -c["n_decisions"])[:top]:
        cols = []
        for a in ACTION_CATEGORIES:
            x = c["actions"][a]
            if "half_width" not in x:
                cols.append(f"{x['mean']:.2f}")
                continue
            ess = "n/a (zero variance)" if x["ess"] is None else f"{x['ess']:.0f}"
            cols.append(f"{x['mean']:.2f} (±{x['half_width']:.2f}, {ess})")
        verdict = "pass" if c["s1_pass"] else "데이터 부족" if c["status"] != "ok" else "fail"
        lines.append(f"| {c['label']} | {c['n_decisions']} | {c['n_games']} | " + " | ".join(cols) + f" | {verdict} |")
    return "\n".join(lines) + "\n"


def write_report(report: dict, out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    j, m = out / "report.json", out / "report.md"
    j.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    m.write_text(to_markdown(report), encoding="utf-8")
    return j, m
