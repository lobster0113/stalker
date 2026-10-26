"""Issue #89 research: how do the data-sufficiency verdicts grow with the number of games?

    python scripts/sufficiency_curve.py --games 100,300,1000 --seed 1 --out DIR [--preset sng6]

Plays max(--games) reference-bot games once. `generate` seeds game i with [seed, i], so the first k games are exactly
the k-game dataset of the same seed; each point re-runs `build_report` (the referee's S1/S4/S5) on that prefix.
Writes DIR/curve.json. Numbers are local and reference-only (CHARTER: only CI results count).

The extrapolation (`required_games`) is a model, not a verdict: per cell it scales the half-dataset cluster
standard error as 1/sqrt(games containing the cell) and asks when the tightest of S1/S4/S5 and the S1 rule of three
would hold. It ignores S4's main-action-agreement condition (near-tied actions) and cells not yet seen.
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Sequence

import numpy as np

from referee.sufficiency import S1_HALF_WIDTH, S4_TOL, S5_FRACTION, S5_TOL
from stalker.pipeline.generate import generate, resolve_config
from stalker.records.schema import DecisionRecord
from stalker.typing.report import build_report
from stalker.typing.spots import ACTION_CATEGORIES, category_probs, spot_key

Z = 1.959964
# Largest per-half standard error each criterion tolerates (both halves are judged):
#   S1: z * se <= 0.05.  S4: |mean_A - mean_B| has sd se*sqrt(2); z*se*sqrt(2) <= 0.05.
#   S5: an 80% subset differs from the full mean with sd se*sqrt(1/0.8 - 1); z * that <= 0.02.
SE_MAX = {"s1": S1_HALF_WIDTH / Z, "s4": S4_TOL / (Z * math.sqrt(2)), "s5": S5_TOL / (Z * math.sqrt(1 / S5_FRACTION - 1))}
FLOOR_GAMES_PER_HALF = math.ceil(3 / S1_HALF_WIDTH)  # rule of three 3/n <= 0.05
TOP_CELLS = 20
HORIZONS = (100, 300, 1000, 3000, 10000, 30000, 100000)  # games at which the model's D1 is reported (calibration)


def _prefix(decisions: Sequence[DecisionRecord], n_games: int) -> list[DecisionRecord]:
    order: dict[str, int] = {}
    out = []
    for r in decisions:
        order.setdefault(r.ids.game_id, len(order))
        if order[r.ids.game_id] < n_games:
            out.append(r)
    return out


def blocking(cell: dict) -> str:
    """Which of S1/S4/S5 fail, e.g. 's1+s5'; 'none' for a lessonable cell."""
    failed = [k for k in ("s1", "s4", "s5") if not cell[k]]
    return "+".join(failed) or "none"


def cluster_se(decisions: Sequence[DecisionRecord], players: int) -> dict[str, tuple[int, float]]:
    """Per cell: (games containing it, max over actions of the game-cluster standard error of the action mean)."""
    per: dict[str, dict[str, np.ndarray]] = {}
    for r in decisions:
        key = spot_key(r, players)
        if key is None:
            continue
        g = per.setdefault(key.label(), {})
        p = category_probs(r)
        acc = g.setdefault(r.ids.game_id, np.zeros(len(ACTION_CATEGORIES) + 1))
        acc[:-1] += [p[a] for a in ACTION_CATEGORIES]
        acc[-1] += 1
    out = {}
    for label, games in per.items():
        a = np.array(list(games.values()))
        y, m = a[:, :-1], a[:, -1:]
        n = len(a)
        if n < 2:
            out[label] = (n, float("inf"))
            continue
        mean = y.sum(axis=0) / m.sum()
        # ratio-estimator cluster variance, the quantity the referee's cluster bootstrap estimates
        var = n / (n - 1) * ((y - m * mean) ** 2).sum(axis=0) / m.sum() ** 2
        out[label] = (n, float(np.sqrt(var.max())))
    return out


def required_games(n_games: int, cell_games: int, se_full: float) -> float:
    """Games needed for one cell to pass every criterion, if it keeps appearing at its current rate."""
    if cell_games < 2 or not math.isfinite(se_full):
        return float("inf")
    rate = cell_games / n_games
    floor = 2 * FLOOR_GAMES_PER_HALF / rate
    se_half = se_full * math.sqrt(2)  # each half has about half the games
    spread = n_games * (se_half / min(SE_MAX.values())) ** 2
    return max(floor, spread)


def extrapolate(report: dict, se: dict[str, tuple[int, float]], n_games: int) -> dict:
    classified = sum(c["n_decisions"] for c in report["cells"])
    need = sorted((required_games(n_games, *se[c["label"]]), c["n_decisions"] / classified) for c in report["cells"])
    out, acc = {}, 0.0
    targets = [0.5, 0.8, 0.95, 0.99]
    for req, share in need:
        acc += share
        while targets and acc >= targets[0] - 1e-12:
            out[f"d1_{targets.pop(0)}"] = req if math.isfinite(req) else None
    for t in targets:
        out[f"d1_{t}"] = None
    # share of today's classified decisions whose cell the model expects to pass by each horizon
    out["predicted_d1"] = {str(h): sum(share for req, share in need if req <= h) for h in HORIZONS}
    out["binding"] = dict(Counter(_binding(n_games, *se[c["label"]]) for c in report["cells"]))
    return out


def _binding(n_games: int, cell_games: int, se_full: float) -> str:
    if cell_games < 2 or not math.isfinite(se_full):
        return "unseen_twice"
    rate = cell_games / n_games
    return "rule_of_three" if 2 * FLOOR_GAMES_PER_HALF / rate >= required_games(n_games, cell_games, se_full) else "spread"


def point(decisions: Sequence[DecisionRecord], players: int, n_games: int, seed: int) -> dict:
    sub = _prefix(decisions, n_games)
    t = time.perf_counter()
    report = build_report(sub, players=players, seed=seed)
    report_s = time.perf_counter() - t
    cells = report["cells"]
    n = len(cells)
    s = report["summary"]
    top = sorted(cells, key=lambda c: (-c["n_decisions"], c["label"]))[:TOP_CELLS]
    return {
        "games": n_games, "decisions": len(sub), "unclassified": report["unclassified"]["count"], "cells": n,
        "lessonable_cells": s["lessonable_cells"],
        "s1_rate": sum(c["s1"] for c in cells) / n if n else 0.0,
        "s4_rate": sum(c["s4"] for c in cells) / n if n else 0.0,
        "s5_rate": sum(c["s5"] for c in cells) / n if n else 0.0,
        "d1_preliminary": s["d1_preliminary"]["lessonable_decision_share"],
        "blocking_cells": dict(Counter(blocking(c) for c in cells)),
        "blocking_decision_share": {k: v / max(len(sub) - report["unclassified"]["count"], 1) for k, v in
                                    _sum_by(cells, blocking).items()},
        "games_per_half_quantiles": _quantiles([min(c["n_games_ab"]) for c in cells]),
        "top_cells": [{"label": c["label"], "n_decisions": c["n_decisions"], "n_games": c["n_games"],
                       "n_games_ab": c["n_games_ab"], "s1": c["s1"], "s4": c["s4"], "s5": c["s5"],
                       "max_half_width": max((x.get("half_width", 0.0) for x in c["actions"].values()), default=0.0)}
                      for c in top],
        "extrapolation": extrapolate(report, cluster_se(sub, players), n_games),
        "report_seconds": report_s,
    }


def _sum_by(cells: list[dict], key) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in cells:
        out[key(c)] = out.get(key(c), 0) + c["n_decisions"]
    return out


def _quantiles(xs: list[int]) -> dict[str, float]:
    if not xs:
        return {}
    return {f"p{q}": float(np.percentile(xs, q)) for q in (50, 90, 99)} | {"max": float(max(xs))}


def run(games: Sequence[int], seed: int, preset: str = "sng6") -> dict:
    if not games or min(games) < 2:
        raise ValueError("--games needs values >= 2: the cluster bootstrap needs two or more games.")
    cfg = resolve_config(preset)
    t = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        decisions = generate(cfg, max(games), seed, tmp)
    gen_s = time.perf_counter() - t
    return {"issue": 89, "preset": cfg.name, "seed": seed, "note": "local, reference only (CI results count)",
            "generation": {"games": max(games), "decisions": len(decisions), "seconds": gen_s,
                           "seconds_per_decision": gen_s / max(len(decisions), 1)},
            "se_max_per_half": SE_MAX, "rule_of_three_games_per_half": FLOOR_GAMES_PER_HALF,
            "points": [point(decisions, cfg.players, g, seed) for g in sorted(set(games))]}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--games", required=True, help="comma-separated game counts, e.g. 100,300,1000")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--preset", default="sng6")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        games = [int(x) for x in a.games.split(",") if x.strip()]
        res = run(games, a.seed, a.preset)
    except ValueError as e:
        ap.error(str(e))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "curve.json").write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for p in res["points"]:
        print(f"{p['games']} games: {p['cells']} cells, lessonable {p['lessonable_cells']}, "
              f"S1 {p['s1_rate']:.3f} S4 {p['s4_rate']:.3f} S5 {p['s5_rate']:.3f}, d1 {p['d1_preliminary']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
