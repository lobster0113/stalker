"""Referee tournament evaluation, record-only (#911, ADR 0026 follow-up 3, ADR 0027 decision 4 / F4).

On a fixed spot set (`tournament_spots_v1.json`: preset x survivors x stack profile x level), one *learning seat* plays
the policy and every other seat is the fixed field (`persona:tag` by default). Per spot (cell) the learning seat's

- `sim_prize`        prize it won in the simulated rest of the tournament (mean, SE over games),
- `icm_equity`       its ICM equity of the start state,
- `corrected_equity` its ADR 0026 bubble-corrected equity at the policy's training lambda (`train_env.lam`),
- `sim_minus_corrected` = sim_prize - corrected_equity (mean, SE),

are recorded as fractions of the prize pool the survivors compete for (never bb), with the #900 backoff counts of
the learning seat (decisions that went to the rule bot instead of the policy). The two equities are fixed by the
start state, so their SE is 0; the sampling error is all in `sim_prize`.

With `lbr_hands` > 0 (`--lbr-hands N`, #917, ADR 0027 F4b) each cell also gets `lbr_pool`: the exploitation gain of an LBR
seat (`referee.e3.lbr.lbr_icm`) against the policy at the learning seat's table position, as a fraction of the
prize pool per hand (mean, SE over N dealt hands), reward = `bubble_corrected_equity` change at the same lambda.
The cell's stacks are the table (E3 chips, BB = 100) in player order, the learner is the LBR seat, every other seat
plays the policy; the policy reads the `t<stage><ante>` slot of the cell. A found gain is a lower bound (chip
one-step LBR decisions, prize-unit reward), never a certificate. Without the option the output is byte-identical to
schema 1; with it `schema_version` is 2.

`policy.by_street` (#964) adds the per-street split of decisions/policy hits. It is an added key only and nothing reads
these files yet, so `schema_version` stays (a reader that ignores unknown keys is unaffected).

No threshold, no verdict: F5 shows the distribution first, then a separate issue sets thresholds (GATES.md).

Cell seeds are children of `SeedSequence(seed)` keyed by the cell (crc32 of the preset name keeps it stable), so
dropping a spot leaves every other cell byte-identical. The key matches `stalker.tools.icm_grid.cell_seed` at
layout 0, but lives here so the referee does not depend on a product tool. Seeds start at 10001 so they never
overlap the training rng (ADR 0027 decision 4).

    python -m referee.e3.tournament_eval --policy result.json --out eval.json [--games 200]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import zlib
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from referee.e3.lbr import lbr_icm
from stalker.agents.e3_policy import E3PolicyAgent, PolicyTable, e3_stage, load_table
from stalker.agents.persona import PersonaAgent, persona_params
from stalker.agents.random_agent import RandomLegalAgent
from stalker.core.icm import bubble_corrected_equity, icm_equity
from stalker.tournament.config import load_preset
from stalker.tournament.director import run_game
from stalker.tournament.start_state import STACK_PROFILES, make_start_state

SCHEMA_VERSION = 1
SCHEMA_VERSION_LBR = 2   # cells carry `lbr_pool`; output without --lbr-hands stays schema 1 byte for byte
MIN_SEED = 10001
DEFAULT_FIELD = "persona:tag"
DEFAULT_GAMES = 200
SPOTS_V1 = Path(__file__).with_name("tournament_spots_v1.json")
SPOT_KEYS = ("preset", "remaining", "profile", "level_index")


def cell_seed(seed: int, spot: dict) -> np.random.SeedSequence:
    key = (zlib.crc32(spot["preset"].encode()), spot["remaining"], STACK_PROFILES.index(spot["profile"]))
    if spot["level_index"]:
        key += (spot["level_index"], 0)
    return np.random.SeedSequence(seed, spawn_key=key)


def load_spots(path: Path = SPOTS_V1) -> list[dict]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return [dict(s) for s in doc["spots"]]


def field_factory(spec: str) -> Callable[[np.random.Generator], object]:
    """One field seat per call: `persona:NAME` or `random`."""
    if spec == "random":
        return lambda rng: RandomLegalAgent(rng)
    kind, _, name = spec.partition(":")
    if kind != "persona" or not name:
        raise ValueError(f"field {spec!r}: use 'persona:NAME' or 'random'.")
    params = persona_params(name)   # bad names fail here with the list of choices
    return lambda rng: PersonaAgent(params, rng)


def _counts(agents: Sequence[E3PolicyAgent]) -> dict:
    """#900 meaning: decisions, policy hits, backoffs (rule bot instead of the policy) and their reasons.

    `by_street` (#964) sums each agent's per-street decisions/policy hits (0 preflop .. 3 river); `hit_rate` is None
    without decisions. Counts from agents that predate it just contribute nothing there."""
    out = {"decisions": 0, "policy_hits": 0, "backoffs": 0, "backoff_reasons": {}}
    streets: dict[str, dict[str, int]] = {}
    for a in agents:
        c = a.counts()
        for k in ("decisions", "policy_hits", "backoffs"):
            out[k] += c[k]
        for r, n in c["backoff_reasons"].items():
            out["backoff_reasons"][r] = out["backoff_reasons"].get(r, 0) + n
        for st, cell in c.get("by_street", {}).items():
            tot = streets.setdefault(str(st), {"decisions": 0, "policy_hits": 0})
            tot["decisions"] += cell["decisions"]
            tot["policy_hits"] += cell["policy_hits"]
    out["backoff_reasons"] = dict(sorted(out["backoff_reasons"].items()))
    out["backoff_rate"] = out["backoffs"] / out["decisions"] if out["decisions"] else None
    out["by_street"] = {st: {**t, "hit_rate": t["policy_hits"] / t["decisions"] if t["decisions"] else None}
                        for st, t in sorted(streets.items())}
    return out


def _stat(x: np.ndarray) -> dict:
    sd = float(x.std(ddof=1))
    return {"mean": float(x.mean()), "se": sd / math.sqrt(x.size)}


def _validate(spots: Sequence[dict], games: int, seed: int, lam: float, lbr_hands: int = 0) -> None:
    if lbr_hands < 0 or lbr_hands == 1:
        raise ValueError(f"lbr_hands={lbr_hands}: use 0 (off) or >= 2 (a standard error needs two hands).")
    if games < 2:
        raise ValueError(f"games={games}: must be >= 2 (each cell needs a standard error).")
    if seed < MIN_SEED:
        raise ValueError(f"seed={seed}: evaluation seeds start at {MIN_SEED} (ADR 0027 decision 4).")
    if not 0.0 <= lam <= 1.0:
        raise ValueError(f"lam={lam}: must be in [0, 1] (ADR 0026).")
    if not spots:
        raise ValueError("no spots: give at least one spot.")
    seen = set()
    for s in spots:
        missing = [k for k in SPOT_KEYS if k not in s]
        if missing:
            raise ValueError(f"spot {s}: missing {missing}; each spot needs {list(SPOT_KEYS)}.")
        if s["profile"] not in STACK_PROFILES:
            raise ValueError(f"spot {s}: profile must be one of {STACK_PROFILES}.")
        key = tuple(s[k] for k in SPOT_KEYS)
        if key in seen:
            raise ValueError(f"spot {s}: listed twice; cells must be unique (they share a seed).")
        seen.add(key)


def _lbr_pool(policy: PolicyTable, config, spot: dict, stacks: Sequence[int], payouts: Sequence[float], seat: int,
              lam: float, hands: int, seed: int) -> dict:
    lv = config.levels[spot["level_index"]]
    e3_stacks = [int(round(s * 100 / lv.bb)) for s in stacks]   # E3 chips: BB = 100
    ante = int(round(lv.ante * 100 / lv.bb)) if config.ante_mode == "bb_ante" else 0
    stage = e3_stage(len(stacks), len(payouts), config.players, config.table_size)
    r = lbr_icm(policy.policy, seat, hands, e3_stacks, payouts, lam, seed, policy.k, policy.depth, ante,
                policy.menu, policy.raise_cap, stage)
    return {"mean": r.mean_bb, "se": r.stderr_bb, "hands": hands, "stage": stage, "ante": ante}


def evaluate_tournament(policy: PolicyTable, spots: Sequence[dict], games: int = DEFAULT_GAMES,
                        seed: int = MIN_SEED, field: str = DEFAULT_FIELD, lam: float = 0.0, lbr_hands: int = 0) -> dict:
    """Per-cell record of the learning seat (see module doc). Same arguments -> identical output."""
    _validate(spots, games, seed, lam, lbr_hands)
    make_field = field_factory(field)
    cells = []
    for spot in spots:
        spot = {k: spot[k] for k in SPOT_KEYS}
        config = load_preset(spot["preset"])
        if not 2 <= spot["remaining"] <= config.players:
            raise ValueError(f"spot {spot}: remaining must be in 2..{config.players}.")
        if not 0 <= spot["level_index"] < len(config.levels):
            raise ValueError(f"spot {spot}: level_index must be in 0..{len(config.levels) - 1}.")
        rng = np.random.default_rng(cell_seed(seed, spot))
        ss = make_start_state(config, rng, spot["remaining"], spot["profile"], spot["level_index"])
        players = sorted(ss.stacks)
        learner = players[int(rng.integers(len(players)))]
        seeds = rng.integers(2**63, size=(games, 3))
        stacks = [ss.stacks[p] for p in players]
        payouts = [float(x) for x in config.payout_amounts()[:len(players)]]
        pool = math.fsum(payouts)
        i = players.index(learner)
        icm = float(icm_equity(stacks, payouts)[i]) / pool
        corrected = float(bubble_corrected_equity(stacks, payouts, lam)[i]) / pool
        prizes, learners = [], []
        for g, (s_field, s_learn, s_game) in enumerate(seeds):
            field_rng = np.random.default_rng(int(s_field))
            agents = [make_field(np.random.default_rng(int(s))) for s in field_rng.integers(2**63, size=config.players)]
            agent = E3PolicyAgent(policy, np.random.default_rng(int(s_learn)), players=config.players,
                                  table_size=config.table_size)
            agents[learner] = agent
            learners.append(agent)
            res = run_game(config, agents, np.random.default_rng(int(s_game)), game_id=f"tev-{g}", start_state=ss)
            prizes.append(res.prizes[learner] / pool)
        sim = np.asarray(prizes, dtype=float)
        cell = {
            **spot, "learner": learner, "players": players, "stacks": stacks, "prize_pool": pool, "games": games,
            "bubble": len(players) == len(payouts) + 1,
            "sim_prize": _stat(sim),
            "icm_equity": {"mean": icm, "se": 0.0},
            "corrected_equity": {"mean": corrected, "se": 0.0},
            "sim_minus_corrected": _stat(sim - corrected),
            "policy": _counts(learners),
        }
        if lbr_hands:
            cell["lbr_pool"] = _lbr_pool(policy, config, spot, stacks, payouts, i, lam, lbr_hands,
                                         int(rng.integers(2**63)))
        cells.append(cell)
    return {"schema_version": SCHEMA_VERSION_LBR if lbr_hands else SCHEMA_VERSION, "unit": "prize_pool_fraction", "games": games, "seed": seed,
            "field": field, "lam": lam, "cells": cells}


def _policy_file(path: Path) -> Path:
    if path.is_dir():
        found = sorted(x for x in path.iterdir() if x.is_file() and x.name.endswith((".json", ".json.gz")))
        if len(found) == 1:
            return found[0]
    return path


def read_train_env(path: Path) -> dict | None:
    """`train_env` of a pod result (top level or its `model` block, #899); None for files without one."""
    from stalker.jsonio import read_json

    doc = read_json(_policy_file(path))
    env = doc.get("train_env") or (doc.get("model") or {}).get("train_env")
    return dict(env) if env else None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(policy_path: Path, spots_path: Path = SPOTS_V1, games: int = DEFAULT_GAMES, seed: int = MIN_SEED,
        field: str = DEFAULT_FIELD, lam: float | None = None, lbr_hands: int = 0) -> dict:
    """Load the policy and spot file, evaluate, and stamp the inputs (hashes, train_env, lambda source)."""
    train_env = read_train_env(policy_path)
    if lam is None:
        lam, lam_source = (float(train_env.get("lam", 0.0)), "train_env") if train_env else (0.0, "default")
    else:
        lam_source = "override"
    out = evaluate_tournament(load_table(policy_path), load_spots(spots_path), games, seed, field, float(lam), lbr_hands)
    out.update(policy={"path": str(policy_path), "sha256": _sha256(_policy_file(policy_path))},
               spots={"path": spots_path.name, "sha256": _sha256(spots_path)},
               train_env=train_env, lam_source=lam_source)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--policy", required=True, type=Path,
                    help="pod result, checkpoint, web policy file, or a folder holding exactly one")
    ap.add_argument("--out", type=Path, help="output JSON (default stdout)")
    ap.add_argument("--spots", type=Path, default=SPOTS_V1, help="spot file (default tournament_spots_v1.json)")
    ap.add_argument("--games", type=int, default=DEFAULT_GAMES, help="games per cell (>= 2)")
    ap.add_argument("--seed", type=int, default=MIN_SEED, help=f"evaluation seed (>= {MIN_SEED})")
    ap.add_argument("--field", default=DEFAULT_FIELD, help="the other seats: persona:NAME or random")
    ap.add_argument("--lam", type=float, help="bubble correction lambda (default: the policy's train_env.lam, else 0)")
    ap.add_argument("--lbr-hands", type=int, default=0, help="also record the ICM-unit LBR per cell over N hands (0 = off)")
    a = ap.parse_args(argv)
    try:
        out = run(a.policy, a.spots, a.games, a.seed, a.field, a.lam, a.lbr_hands)
    except (ValueError, FileNotFoundError, KeyError) as e:
        ap.exit(2, f"tournament_eval: {e}\n")
    text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
