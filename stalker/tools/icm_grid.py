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
"""
from __future__ import annotations

import argparse
import json
import math
import zlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from stalker.tools.icm_calibration import agents_factory, calibrate
from stalker.tournament.config import load_preset
from stalker.tournament.start_state import STACK_PROFILES, make_start_state

SCHEMA_VERSION = 1
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


def run_grid(presets: Sequence[str], remainings: Sequence[int], profiles: Sequence[str], games: int,
             seed: int, agents: str = "random", level_indexes: Sequence[int] = (0,), layouts: int = 1) -> dict:
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
    v2 = tuple(level_indexes) != (0,) or layouts != 1
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
                        cells.append({**key, **extra, **summarize(raw), "calibrate": raw})
    grid = {"schema_version": 2 if v2 else SCHEMA_VERSION, "seed": seed, "games": games, "cells": cells,
            "skipped": skipped}
    if v2:
        grid["level_indexes"] = list(level_indexes)
        grid["layouts"] = layouts
    if factory is not None:
        grid["agents"] = agents
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
        grid = run_grid(_csv(a.presets), remainings, _csv(a.profiles), a.games, a.seed, a.agents, levels, a.layouts)
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
