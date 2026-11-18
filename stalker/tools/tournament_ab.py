"""Tournament A/B evaluation of two trained E3 policies (#907, ADR 0027 decision 4).

Primary metric, per cell (preset x survivors x stack profile x level x layout): one *learning seat* plays arm A or arm
B, every other seat is the fixed field (`persona:tag` by default), and the seat's **simulated prize minus its ICM
equity** is averaged over the games, in units of the prize pool the survivors compete for (never bb). A and B use the
same start state, the same learning seat and the same per-game seeds (common random numbers), so their difference is
paired game by game; with the same policy on both arms it is exactly 0.

The headline is the mean over cells of the per-cell B - A mean, with SE = sqrt(sum of per-cell SE^2) / cells and a
normal 95% CI. Adoption rule: B when the CI's lower bound is above 0, otherwise A (a tie is A, i.e. cold).

Auxiliary, per cell and arm: the ADR 0026 metrics of a policy-symmetric field (the arm on every seat, via
`icm_calibration.calibrate` and `icm_grid.lambda_metrics` at lambda = 0; summary (i) significant bubble cells and
(ii) mean bubble |diff|/pool), and the #900 backoff counts of the learning seat (`policy`) and of the symmetric field.
The unvisited-key list (`missing_keys`, #990) is kept only in the per-arm totals `policy.<arm>`; per-cell `policy`
entries drop it (schema 2, #1004) so the result stays under the ops upload limit whatever the cell count.
Every `policy` entry (totals and cells) also splits decisions, hits and reasons by the hand's player count,
`by_players` ({"2": {...}, "4": {...}}, schema 3, #1010): a few small cells, so the bubble's own backoff can be
told apart from a bubble-only table used heads-up.

    python -m stalker.tools.tournament_ab --a cold.json --b prior.json --presets 9max_sng_503020 --remaining 4 \
        --profiles even,random,skewed --layouts 3 --games 200 --seed 10001 --out ab.json

Cell seeds come from the cell key (`icm_grid.cell_seed`), so dropping a cell leaves the others byte-identical.
Evaluation seeds start at 10001 so they never overlap the training rng (decision 4).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from stalker.agents.e3_policy import E3PolicyAgent
from stalker.core.icm import icm_equity
from stalker.tools.icm_calibration import PolicyAgents, agents_factory, calibrate
from stalker.tools.icm_grid import (
    cell_seed,
    lambda_metrics,
    summarize,
    summarize_lambdas,
    zone,
)
from stalker.tournament.config import load_preset
from stalker.tournament.director import run_game
from stalker.tournament.start_state import STACK_PROFILES, make_start_state

SCHEMA_VERSION = 3   # 2: per-cell policy counts without missing_keys (#1004); 3: policy.by_players (#1010)
DEFAULT_SEED = 10001
DEFAULT_FIELD = "persona:tag"
Z95 = 1.959963984540054
ARMS = ("A", "B")
ADOPTED = {"A": "cold", "B": "prior"}


def mean_ci(diffs: Sequence[Sequence[float]], z: float = Z95) -> dict:
    """Mean over cells of each cell's mean paired difference; SE = sqrt(sum se_c^2) / cells, se_c = sd_c / sqrt(n_c)
    (ddof 1). Every cell needs >= 2 samples."""
    if not diffs:
        raise ValueError("no cells: give at least one cell with games >= 2.")
    means, var = [], 0.0
    for d in diffs:
        d = np.asarray(d, dtype=float)
        if d.size < 2:
            raise ValueError(f"a cell has {d.size} sample(s): games must be >= 2 for a standard error.")
        means.append(float(d.mean()))
        var += float(d.var(ddof=1)) / d.size
    c = len(means)
    mean = math.fsum(means) / c
    se = math.sqrt(var) / c
    return {"mean": mean, "se": se, "ci_low": mean - z * se, "ci_high": mean + z * se, "cells": c}


def verdict(ci_low: float) -> str:
    """ADR 0027 decision 4: B only when the 95% CI's lower bound is strictly above 0; a tie stays A (cold)."""
    return "B" if ci_low > 0 else "A"


def _policy_file(path: str) -> Path:
    p = Path(path)
    if p.is_dir():
        found = sorted(x for x in p.iterdir() if x.is_file() and x.name.endswith((".json", ".json.gz")))
        if len(found) == 1:
            return found[0]
    return p


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _play_arm(config, ss, arm: PolicyAgents, field, learner: int, seeds: np.ndarray, pool: float,
              icm: float) -> list[float]:
    """Per game: (learning seat's prize - its ICM equity) / pool."""
    out = []
    for g, (s_field, s_learn, s_game) in enumerate(seeds):
        agents = list(field(config, np.random.default_rng(int(s_field))))
        agent = E3PolicyAgent(arm.table, np.random.default_rng(int(s_learn)), players=config.players,
                              table_size=config.table_size)
        arm.agents.append(agent)
        agents[learner] = agent
        res = run_game(config, agents, np.random.default_rng(int(s_game)), game_id=f"ab-{g}", start_state=ss)
        out.append((res.prizes[learner] - icm) / pool if pool else 0.0)
    return out


def _cell_counts(arm: PolicyAgents) -> dict:
    """Per-cell counts: 36 copies of the top-N key lists pushed a 9-cell run past ops' 1 MiB (#1004)."""
    c = arm.counts()
    c.pop("missing_keys", None)
    return c


def _symmetric(config, ss, arm: PolicyAgents, games: int, seed: int) -> dict:
    arm.reset()
    raw = calibrate(config, ss, arm, games, np.random.default_rng(seed))
    (m,) = lambda_metrics(raw, [0.0])
    return {"games": games, "zone": zone(raw), **summarize(raw), "significant": m["significant"],
            "lambda_metrics": [m], "policy": _cell_counts(arm)}


def run_ab(a: str, b: str, presets: Sequence[str], remainings: Sequence[int], profiles: Sequence[str], games: int,
           seed: int = DEFAULT_SEED, layouts: int = 1, level_indexes: Sequence[int] = (0,),
           field: str = DEFAULT_FIELD, sym_games: int | None = None) -> dict:
    if games < 2:
        raise ValueError(f"games={games}: must be >= 2 (the CI needs a standard error per cell).")
    sym_games = games if sym_games is None else sym_games
    if sym_games < 0:
        raise ValueError(f"sym_games={sym_games}: must be >= 0 (0 skips the symmetric-field metrics).")
    if layouts < 1:
        raise ValueError(f"layouts={layouts}: must be >= 1.")
    for p in profiles:
        if p not in STACK_PROFILES:
            raise ValueError(f"profile {p!r}: must be one of {STACK_PROFILES}.")
    if field.startswith("policy:"):
        raise ValueError(f"--field {field!r}: the field must be 'random' or 'persona:NAME'.")
    field_factory = agents_factory(field)
    arms = {"A": PolicyAgents(a), "B": PolicyAgents(b)}
    configs = {name: load_preset(name) for name in presets}
    for name, config in configs.items():
        for lv in level_indexes:
            if not 0 <= lv < len(config.levels):
                raise ValueError(f"level_index={lv}: {name} has levels 0..{len(config.levels) - 1}.")
    learners: dict[str, list] = {k: [] for k in ARMS}   # every learning-seat agent, for the per-arm totals
    cells, skipped, diffs = [], [], []
    for preset in presets:
        config = configs[preset]
        for remaining in remainings:
            for profile in profiles:
                key = {"preset": preset, "remaining": remaining, "profile": profile}
                if not 2 <= remaining <= config.players:
                    skipped.append({**key, "reason": f"remaining={remaining}: must be in 2..{config.players}."})
                    continue
                for lv in level_indexes:
                    for k in range(layouts):
                        rng = np.random.default_rng(cell_seed(seed, preset, remaining, profile, lv, k))
                        ss = make_start_state(config, rng, remaining, profile, lv)
                        players = sorted(ss.stacks)
                        learner = players[int(rng.integers(len(players)))]
                        seeds = rng.integers(2**63, size=(games, 3))
                        sym_seed = int(rng.integers(2**63))
                        stacks = [ss.stacks[p] for p in players]
                        payouts = [float(x) for x in config.payout_amounts()[:len(players)]]
                        pool = math.fsum(payouts)
                        icm = float(icm_equity(stacks, payouts)[players.index(learner)])
                        cell = {**key, "level_index": lv, "layout": k, "learner": learner, "players": players,
                                "stacks": stacks, "prize_pool": pool, "learner_icm_rel": icm / pool if pool else 0.0,
                                "games": games, "arms": {}}
                        rel = {}
                        for name in ARMS:
                            arm = arms[name]
                            arm.reset()
                            rel[name] = _play_arm(config, ss, arm, field_factory, learner, seeds, pool, icm)
                            learners[name] += arm.agents
                            x = np.asarray(rel[name])
                            entry = {"mean": float(x.mean()), "sd": float(x.std(ddof=1)), "policy": _cell_counts(arm)}
                            if sym_games:
                                entry["symmetric"] = _symmetric(config, ss, arm, sym_games, sym_seed)
                            cell["arms"][name] = entry
                        d = np.asarray(rel["B"]) - np.asarray(rel["A"])
                        diffs.append(d)
                        cell["diff_b_minus_a"] = {"mean": float(d.mean()), "sd": float(d.std(ddof=1)),
                                                  "se": float(d.std(ddof=1)) / math.sqrt(games)}
                        cells.append(cell)
    totals = {}
    for name in ARMS:
        arms[name].agents = learners[name]
        totals[name] = arms[name].counts()
    primary = mean_ci(diffs)
    v = verdict(primary["ci_low"])
    out = {
        "schema_version": SCHEMA_VERSION,
        "args": {"a": a, "b": b, "presets": list(presets), "remaining": list(remainings), "profiles": list(profiles),
                 "level_indexes": list(level_indexes), "layouts": layouts, "games": games, "sym_games": sym_games,
                 "seed": seed, "field": field},
        "agents": {name: {"path": p, "sha256": _sha256(_policy_file(p))} for name, p in (("A", a), ("B", b))},
        "unit": "prize_pool_fraction",
        "primary": {"metric": "learner sim prize - ICM equity (B - A)", **primary},
        "verdict": v,
        "adopted": ADOPTED[v],
        "policy": totals,
        "cells": cells,
        "skipped": skipped,
    }
    if sym_games:
        out["symmetric_summary"] = {}
        for name in ARMS:
            sym = [{"zone": c["arms"][name]["symmetric"]["zone"],
                    "lambda_metrics": c["arms"][name]["symmetric"]["lambda_metrics"]} for c in cells]
            (row,) = summarize_lambdas(sym, [0.0])
            out["symmetric_summary"][name] = {"i_bubble_significant": row["bubble_significant"],
                                              "ii_bubble_mean_rel": row["bubble_mean_rel"], **row}
    return out


def _csv(text: str) -> list[str]:
    return [s.strip() for s in text.split(",") if s.strip()]


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--a", required=True, help="arm A policy (pod result, checkpoint, web policy file or folder)")
    ap.add_argument("--b", required=True, help="arm B policy")
    ap.add_argument("--presets", required=True, help="comma-separated preset names")
    ap.add_argument("--remaining", required=True, help="comma-separated survivor counts")
    ap.add_argument("--profiles", default=",".join(STACK_PROFILES), help="comma-separated stack profiles")
    ap.add_argument("--layouts", type=int, default=1, help="survivor/stack layouts per cell (default 1)")
    ap.add_argument("--level-index", default="0", help="comma-separated start blind levels (default 0)")
    ap.add_argument("--games", type=int, default=200, help="games per cell and arm (>= 2)")
    ap.add_argument("--sym-games", type=int, help="games per cell and arm for the symmetric-field metrics "
                                                  "(default --games, 0 skips them)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--field", default=DEFAULT_FIELD, help="the other seats: persona:NAME or random")
    ap.add_argument("--out", type=Path)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    try:
        remainings = [int(x) for x in _csv(a.remaining)]
        levels = [int(x) for x in _csv(a.level_index)]
    except ValueError:
        ap.error("--remaining and --level-index take comma-separated integers, e.g. 4 or 0,6.")
    try:
        out = run_ab(a.a, a.b, _csv(a.presets), remainings, _csv(a.profiles), a.games, a.seed, a.layouts, levels,
                     a.field, a.sym_games)
    except (ValueError, FileNotFoundError, KeyError) as e:
        ap.exit(2, f"tournament_ab: {e}\n")
    text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
