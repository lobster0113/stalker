"""ICM calibration over a grid of preset x survivors x stack profile (#844, follow-up B of #834).

One `icm_calibration.calibrate` run per cell, summarised as the largest gap between simulated prize mean and ICM
equity: absolute, relative to the pool the survivors compete for, and in standard errors. The table shows where ICM
bias is large enough to matter before anyone builds a tournament evaluation on it. Only the v1 output fields
(`diff`, `sim_prize_sd`, `prize_pool`, `games`) are read, so the summary does not depend on #843's additions.

Cell seeds come from the cell's key, not its position: removing a preset, survivor count or profile from the grid
leaves every other cell's output byte-identical, so a partial rerun can be compared with a full one.

    python -m stalker.tools.icm_grid --presets 6max_sng_topheavy,9max_sng_503020 --remaining 2,3,4 \
        --profiles even,random,skewed --games 200 --seed 0 --out grid.json --md grid.md [--agents persona:tag]

`--agents` picks who plays every seat (`random` default, or `persona:NAME` via `icm_calibration.agents_factory`).
The default writes no `agents` field, so outputs from before the option existed stay byte-identical (#845).

`--level-index 0,6` starts the cells at each blind level and `--layouts N` draws N independent survivor/stack layouts
per cell (#858). Level 0 / layout 0 keeps the pre-option seed and output; any other choice writes schema_version 2 with
`level_index` and `layout` on every cell. Layout k's seed is the cell key plus (level, k), so dropping a level or a
layout leaves the others byte-identical.

`--lambda-grid` (bare = 0,0.05,0.1,0.2,0.35,0.5) re-scores every cell's *same* simulation against the ADR 0026
bubble-corrected equity for each lambda and picks one by the ADR's step-4 rule (#866); it writes schema_version 3 with
`lambda_grid`, per-cell `zone` / `lambda_metrics`, `lambda_summary` and `selected_lambda`. Without the flag the output
is unchanged. The simulation never depends on the lambda list, so changing it leaves `sim_prize_mean` byte-identical.
"""
from __future__ import annotations

import argparse
import json
import math
import zlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from stalker.core.icm import ICMError, bubble_corrected_equity
from stalker.tools.icm_calibration import agents_factory, calibrate
from stalker.tournament.config import load_preset
from stalker.tournament.start_state import STACK_PROFILES, make_start_state

SCHEMA_VERSION = 1
LAMBDA_SCHEMA_VERSION = 3
DEFAULT_LAMBDA_GRID = (0.0, 0.05, 0.1, 0.2, 0.35, 0.5)
SIG_Z, SIG_REL = 3.0, 0.02  # ADR 0026: a cell is significant when |z| >= 3 and |diff|/pool >= 0.02
MD_NOTE = "로컬 참고값, CI 결과 아님"


def cell_seed(seed: int, preset: str, remaining: int, profile: str, level_index: int = 0,
              layout: int = 0) -> np.random.SeedSequence:
    """Child of SeedSequence(seed) whose spawn key is the cell key (crc32 keeps preset names stable across runs).
    Level 0 / layout 0 uses the v1 key so old outputs reproduce."""
    key = (zlib.crc32(preset.encode()), remaining, STACK_PROFILES.index(profile))
    if level_index or layout:
        key += (level_index, layout)
    return np.random.SeedSequence(seed, spawn_key=key)


def summarize(raw: dict) -> dict:
    diff = np.abs(np.asarray(raw["diff"], dtype=float))
    se = np.asarray(raw["sim_prize_sd"], dtype=float) / math.sqrt(raw["games"])
    z = np.divide(diff, se, out=np.zeros_like(diff), where=se != 0)
    pool = raw["prize_pool"]
    return {
        "max_abs_diff": float(diff.max()),
        "max_abs_diff_rel": float(diff.max() / pool) if pool else 0.0,
        "max_abs_z": float(z.max()),
    }


def parse_lambda_grid(text: str) -> list[float]:
    try:
        grid = [float(x) for x in text.split(",") if x.strip()]
    except ValueError:
        raise ValueError(f"--lambda-grid {text!r}: use comma-separated numbers, e.g. 0,0.1,0.5.") from None
    return validate_lambda_grid(grid)


def validate_lambda_grid(grid: Sequence[float]) -> list[float]:
    grid = [float(x) for x in grid]
    if 0.0 not in grid:
        raise ValueError("lambda grid must include 0: lambda=0 (pure ICM) is the baseline the rule compares to.")
    if len(set(grid)) != len(grid):
        raise ValueError(f"lambda grid {grid} has duplicates.")
    bad = [x for x in grid if not 0.0 <= x <= 1.0]
    if bad:
        raise ValueError(f"lambda grid values must be in [0, 1] (ADR 0026), got {bad}.")
    return grid


def zone(raw: dict) -> str:
    """bubble = one more live player than paid places; in_prize = live players all inside the paid places."""
    live = sum(1 for s in raw["stacks"] if s > 0)
    paid = len(raw["payouts"])
    return "bubble" if live == paid + 1 else "in_prize" if live <= paid else "other"


def lambda_metrics(raw: dict, lambdas: Sequence[float]) -> list[dict]:
    """Per lambda: survivors' max |sim mean - corrected equity| / pool and max z, from the cell's one simulation."""
    mean = np.asarray(raw["sim_prize_mean"], dtype=float)
    se = np.asarray(raw["sim_prize_sd"], dtype=float) / math.sqrt(raw["games"])
    alive = np.asarray(raw["stacks"]) > 0
    pool = raw["prize_pool"]
    out = []
    for lam in lambdas:
        try:
            eq = np.asarray(bubble_corrected_equity(raw["stacks"], raw["payouts"], lam), dtype=float)
        except ICMError as e:
            raise ValueError(str(e)) from None
        diff = np.abs(mean - eq)[alive]
        z = np.divide(diff, se[alive], out=np.zeros_like(diff), where=se[alive] != 0)
        rel = float(diff.max() / pool) if pool else 0.0
        zmax = float(z.max())
        out.append({"lambda": lam, "max_abs_diff_rel": rel, "max_abs_z": zmax,
                    "significant": bool(zmax >= SIG_Z and rel >= SIG_REL)})
    return out


def summarize_lambdas(cells: Sequence[dict], lambdas: Sequence[float]) -> list[dict]:
    """ADR 0026 step 3: per lambda (i) significant bubble cells, (ii) mean bubble |diff|/pool, (iii) significant
    in-prize cells."""
    rows = []
    for i, lam in enumerate(lambdas):
        bubble = [c["lambda_metrics"][i] for c in cells if c["zone"] == "bubble"]
        prize = [c["lambda_metrics"][i] for c in cells if c["zone"] == "in_prize"]
        rows.append({"lambda": lam, "bubble_cells": len(bubble),
                     "bubble_significant": sum(m["significant"] for m in bubble),
                     "bubble_mean_rel": math.fsum(m["max_abs_diff_rel"] for m in bubble) / len(bubble) if bubble else 0.0,
                     "in_prize_cells": len(prize),
                     "in_prize_significant": sum(m["significant"] for m in prize)})
    return rows


def select_lambda(summary: Sequence[dict]) -> float:
    """ADR 0026 step 4. Candidates: in-prize significant cells not above lambda=0's. Best = fewest significant bubble
    cells, then smallest mean bubble |diff|/pool, then smallest lambda. If that does not beat lambda=0 on the first
    criterion, pure ICM (0) stays."""
    base = next(r for r in summary if r["lambda"] == 0)
    cands = [r for r in summary if r["in_prize_significant"] <= base["in_prize_significant"]]
    best = min(cands, key=lambda r: (r["bubble_significant"], r["bubble_mean_rel"], r["lambda"]))
    return float(best["lambda"]) if best["bubble_significant"] < base["bubble_significant"] else 0.0


def run_grid(presets: Sequence[str], remainings: Sequence[int], profiles: Sequence[str], games: int,
             seed: int, agents: str = "random", level_indexes: Sequence[int] = (0,), layouts: int = 1,
             lambda_grid: Sequence[float] | None = None) -> dict:
    lambdas = None if lambda_grid is None else validate_lambda_grid(lambda_grid)
    factory = None if agents == "random" else agents_factory(agents)
    for p in profiles:
        if p not in STACK_PROFILES:
            raise ValueError(f"profile {p!r}: must be one of {STACK_PROFILES}.")
    if layouts < 1:
        raise ValueError(f"layouts={layouts}: must be >= 1.")
    configs = {name: load_preset(name) for name in presets}
    for name, config in configs.items():
        for lv in level_indexes:
            if not 0 <= lv < len(config.levels):
                raise ValueError(f"level_index={lv}: {name} has levels 0..{len(config.levels) - 1}.")
    v2 = tuple(level_indexes) != (0,) or layouts != 1 or lambdas is not None  # v3 carries the v2 fields too
    cells, skipped = [], []
    for preset in presets:
        config = configs[preset]
        for remaining in remainings:
            for profile in profiles:
                key = {"preset": preset, "remaining": remaining, "profile": profile}
                if remaining < 2:
                    skipped.append({**key, "reason": f"remaining={remaining} < 2: nothing left to calibrate."})
                    continue
                if remaining > config.players:
                    skipped.append({**key, "reason": f"remaining={remaining} > players={config.players}."})
                    continue
                for lv in level_indexes:
                    for k in range(layouts):
                        rng = np.random.default_rng(cell_seed(seed, preset, remaining, profile, lv, k))
                        ss = make_start_state(config, rng, remaining, profile, lv)
                        raw = calibrate(config, ss, factory, games, rng)
                        extra = {"level_index": lv, "layout": k} if v2 else {}
                        lam = ({"zone": zone(raw), "lambda_metrics": lambda_metrics(raw, lambdas)}
                               if lambdas else {})
                        cells.append({**key, **extra, **summarize(raw), **lam, "calibrate": raw})
    grid = {"schema_version": LAMBDA_SCHEMA_VERSION if lambdas else 2 if v2 else SCHEMA_VERSION, "seed": seed, "games": games, "cells": cells,
            "skipped": skipped}
    if v2:
        grid["level_indexes"] = list(level_indexes)
        grid["layouts"] = layouts
    if factory is not None:
        grid["agents"] = agents
    if lambdas:
        summary = summarize_lambdas(cells, lambdas)
        grid.update({"lambda_grid": lambdas, "lambda_summary": summary, "selected_lambda": select_lambda(summary)})
    return grid


def to_markdown(grid: dict) -> str:
    head = MD_NOTE if "agents" not in grid else f"{MD_NOTE} (agents={grid['agents']})"
    v2 = grid["schema_version"] >= 2
    cols = "| preset | remaining | profile |" + (" level | layout |" if v2 else "") + " max\\|diff\\|/pool | max\\|z\\| |"
    lines = [head, "", cols, "|---|---:|---|" + ("---:|---:|" if v2 else "") + "---:|---:|"]
    for c in grid["cells"]:
        lv = f" {c['level_index']} | {c['layout']} |" if v2 else ""
        lines.append(f"| {c['preset']} | {c['remaining']} | {c['profile']} |{lv} {c['max_abs_diff_rel']:.4f} "
                     f"| {c['max_abs_z']:.2f} |")
    if "lambda_summary" in grid:
        lines += ["", f"selected λ = {grid['selected_lambda']}", "",
                  "| λ | bubble cells | bubble significant | bubble mean \\|diff\\|/pool | in-prize significant |",
                  "|---:|---:|---:|---:|---:|"]
        lines += [f"| {r['lambda']} | {r['bubble_cells']} | {r['bubble_significant']} | {r['bubble_mean_rel']:.4f} "
                  f"| {r['in_prize_significant']} |" for r in grid["lambda_summary"]]
    return "\n".join(lines) + "\n"


def _csv(text: str) -> list[str]:
    return [s.strip() for s in text.split(",") if s.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--presets", required=True, help="comma-separated preset names")
    ap.add_argument("--remaining", required=True, help="comma-separated survivor counts")
    ap.add_argument("--profiles", default=",".join(STACK_PROFILES), help="comma-separated stack profiles")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--level-index", default="0", help="comma-separated start blind levels (default 0)")
    ap.add_argument("--layouts", type=int, default=1, help="survivor/stack layouts per cell (default 1)")
    ap.add_argument("--lambda-grid", nargs="?", const=",".join(str(x) for x in DEFAULT_LAMBDA_GRID),
                    help="bubble-correction lambdas to score and select from (bare flag = 0,0.05,0.1,0.2,0.35,0.5; "
                         "must include 0)")
    ap.add_argument("--agents", default="random", help="random | persona:NAME (every seat)")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--md", type=Path)
    a = ap.parse_args(argv)
    try:
        remainings = [int(x) for x in _csv(a.remaining)]
    except ValueError:
        ap.error(f"--remaining {a.remaining!r}: use comma-separated integers, e.g. 2,3,4.")
    try:
        levels = [int(x) for x in _csv(a.level_index)]
    except ValueError:
        ap.error(f"--level-index {a.level_index!r}: use comma-separated integers, e.g. 0,6.")
    try:
        lambdas = parse_lambda_grid(a.lambda_grid) if a.lambda_grid is not None else None
        grid = run_grid(_csv(a.presets), remainings, _csv(a.profiles), a.games, a.seed, a.agents, levels, a.layouts,
                        lambdas)
    except (ValueError, FileNotFoundError, KeyError) as e:
        ap.exit(2, f"icm_grid: {e}\n")
    text = json.dumps(grid, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    if a.md:
        a.md.write_text(to_markdown(grid), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
