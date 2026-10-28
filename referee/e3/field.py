"""E3 6-max duplicate field evaluation: "max loss vs opponent set" (#295, referee/GATES.md Gate Q, ADR 0015).

One target policy sits with five opponents from a pre-registered configuration (`field_v1.json`,
recorded with its sha256). Duplicate: every deal is played once per seat rotation - the target takes
each seat's cards in turn and the opponents fill the other seats in their listed order, starting
after the target - with the same action random stream in every rotation. When every seat plays the
same policy the hand is identical in all rotations, so the target collects each seat's payoff once
and the deal sums to zero exactly (the symmetry check). The CI resamples whole deals
(`referee.stats.bootstrap_ci`; a deal is the cluster of its rotations).

Opponent kinds: a persona name (`stalker.e3.personas`), "uniform" (uniform over the legal actions),
"self" (the target policy). A TP-key policy (dict, as trained by `stalker.e3.mccfr`) is read the way
it was trained: its public ranges are its own beliefs - every seat Bayes-updated with the policy's
strategy, whatever that seat really plays - as `referee.e3.lbr` reads it. Persona and uniform
targets need no beliefs.

Reported per configuration: the target's bb/100 and its 95% CI; then the worst configuration
(lowest mean) with its point estimate and CI lower bound. This is a measured loss against this
opponent set, not an exploitability bound (no Q4 here).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from referee.e3.lbr import seat_probs
from referee.stats import bootstrap_ci
from stalker.e2.eq_view import combo_index
from stalker.e3 import game as G
from stalker.e3 import tp_key as K

CONFIGS_V1 = Path(__file__).resolve().parent / "field_v1.json"
SPECIAL = ("uniform", "self")


class FieldError(ValueError):
    pass


def load(path: Path = CONFIGS_V1) -> tuple[dict, str]:
    from stalker.agents.persona import PRESETS

    raw = path.read_bytes()
    spec = json.loads(raw)
    if not spec.get("configs"):
        raise FieldError(f"{path.name}: no configs; list opponent configurations under 'configs'")
    known = set(PRESETS) | set(SPECIAL)
    for c in spec["configs"]:
        if len(c["opponents"]) != spec["players"] - 1:
            raise FieldError(f"{path.name}: config {c['name']!r} has {len(c['opponents'])} opponents; "
                             f"need {spec['players'] - 1}")
        bad = [o for o in c["opponents"] if o not in known]
        if bad:
            raise FieldError(f"{path.name}: config {c['name']!r} names unknown opponents {bad}; use {sorted(known)}")
    return spec, hashlib.sha256(raw).hexdigest()


def uniform(s: G.State) -> np.ndarray:
    m = len(G.legal(s))
    return np.full(m, 1.0 / m)


def _actor(kind: str, target):
    if kind == "self":
        return target
    if kind == "uniform":
        return uniform
    from stalker.e3.personas import Persona

    return Persona(kind)


def play_deal(target, opponents: list, deal_seed: int, k: int = 5, depth: str = "basic") -> np.ndarray:
    """The target's net (bb) in each seat rotation of one deal. `target`: a TP-key policy dict or a
    callable state -> probabilities over the legal actions; `opponents`: one actor per other seat."""
    n = len(opponents) + 1
    tp = target if isinstance(target, dict) else None
    out = np.empty(n)
    for seat in range(n):
        s = G.deal(np.random.default_rng([deal_seed, 0]), n)
        rng = np.random.default_rng([deal_seed, 1])      # the same action stream in every rotation
        actors = {seat: target}
        for j, opp in enumerate(opponents):
            actors[(seat + 1 + j) % n] = opp
        ranges = K.initial_ranges(n) if tp is not None else None
        while not s.done:
            p, acts = s.to_act, G.legal(s)
            table = seat_probs(tp, s, p, ranges, k, depth) if tp is not None else None
            who = actors[p]
            row = table[combo_index(s.hole[p])] if who is tp else who(s)
            a = int(rng.choice(len(acts), p=row / row.sum()))
            if tp is not None:
                ranges = K.update_range(ranges, p, table[:, a])
            s = G.apply(s, acts[a])
        out[seat] = float(G.payoff(s)[seat]) / G.BB
    return out


def evaluate(target, hands: int, seed: int = 0, spec: dict | None = None, k: int = 5, depth: str = "basic",
             configs: list[str] | None = None) -> dict:
    """The target's bb/100 per configuration (95% CI over deals) and the worst configuration."""
    sha = None
    if spec is None:
        spec, sha = load()
    if hands < 2:
        raise ValueError("hands must be >= 2 (the CI resamples deals)")
    rows = []
    for c in spec["configs"]:
        if configs and c["name"] not in configs:
            continue
        opps = [_actor(o, target) for o in c["opponents"]]
        res = np.array([play_deal(target, opps, seed * 1_000_003 + h, k, depth) for h in range(hands)])
        ci = bootstrap_ci(res.ravel() * 100, np.repeat(np.arange(hands), res.shape[1]), rng=np.random.default_rng(seed))
        rows.append({"name": c["name"], "bb100": round(ci.mean, 2), "ci95": [round(ci.lo, 2), round(ci.hi, 2)],
                     "deals": hands, "by_seat_bb100": [round(float(x), 1) for x in res.mean(axis=0) * 100]})
    if not rows:
        raise FieldError(f"no config matched {configs}")
    worst = min(rows, key=lambda r: r["bb100"])
    return {"version": spec["version"], "sha256": sha, "seed": seed, "deals": hands, "configs": rows,
            "worst": {"name": worst["name"], "bb100": worst["bb100"], "ci95_low": worst["ci95"][0]}}


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="E3 6-max field evaluation of a TP-key policy (bb/100, worst configuration)")
    ap.add_argument("policy", type=Path, help="policy JSON: a dict of TP keys, or {'average': ..., 'current': ...}")
    ap.add_argument("--which", default="current", choices=["current", "average"])
    ap.add_argument("--tier", default="beginner", choices=sorted(K.TIER_K))
    ap.add_argument("--hands", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--configs", nargs="*")
    a = ap.parse_args(argv)
    pol = json.loads(a.policy.read_text(encoding="utf-8"))
    if isinstance(pol.get(a.which), dict):
        pol = pol[a.which]
    res = evaluate(pol, a.hands, a.seed, k=K.TIER_K[a.tier], depth=K.TIER_DEPTH[a.tier], configs=a.configs)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
