"""How often the browser's c1 policy table has a row for the actor's real hand (#611).

The page's AI seats act from `web/app/policy/<tier>-<n>.json` and play uniformly where the table has no row
(`tpgto.js actionProbs`). Seeded hands of the table's seat count are played with that rule through the engine
(`stalker.e3.game`); at every decision the actor's real c1 key (`tp_key.key(public_key(variant="c1"), step)`) is
looked up. The output counts decisions and hits per street (0..3) and for call-or-fold `call|` keys. With a
checkpoint (`--pod-result`, as `export_web_players`) it also gives the same table for `min_visits` candidates:
a key hits when the table has it and the checkpoint saw it that often.

    python -m stalker.tools.web_hit_rate web/app/policy/mid-3.json --hands 1000 --seed 611
    python -m stalker.tools.web_hit_rate web/app/policy/mid-3.json --pod-result result.json

Reference measurements only; CI numbers are the ones that count.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from stalker.e2.eq_view import N
from stalker.e3 import game as G
from stalker.e3 import tp_key as K

SCHEMA = "stalker.web.hit-rate"
SCHEMA_VERSION = 1
MIN_VISITS = (0, 1, 2, 5, 10)


def load_policy(path: Path) -> tuple[dict, dict]:
    """A web policy file -> (key -> probability row, the file's header)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    q = doc["q"]
    return {k: [x / q for x in row] for k, row in doc["policy"].items()}, doc


def _cell() -> dict:
    return {"decisions": 0, "hits": 0}


def _bump(cells: dict, name: str, hit: bool) -> None:
    c = cells.setdefault(name, _cell())
    c["decisions"] += 1
    c["hits"] += int(hit)


def _rate(c: dict) -> dict:
    return {**c, "rate": c["hits"] / c["decisions"] if c["decisions"] else None}


def _row(policy: dict, key: str, m: int):
    p = policy.get(key)
    return p if p is not None and len(p) == m else None


def measure(policy: dict, players: int, tier_k: int, depth: str, hands: int, seed: int,
            visits: dict | None = None, min_visits=MIN_VISITS) -> dict:
    """Play `hands` seeded hands; the table's row (uniform when absent) drives every seat, as the page does."""
    rng = np.random.default_rng([seed, 611, players])
    by_street = {str(st): _cell() for st in range(4)}
    kinds = {"call": _cell(), "other": _cell()}
    cand = {str(v): {"street": {str(st): _cell() for st in range(4)}, "call": _cell(), "other": _cell()}
            for v in min_visits} if visits is not None else {}
    for _ in range(hands):
        s = G.deal(rng, players, stacks=G.sample_stacks(rng, players, equal_p=1.0))
        ranges = K.initial_ranges(players)
        while not s.done:
            acts, p = G.legal(s), s.to_act
            m = len(acts)
            public = K.public_key(s, p, depth, variant="c1")
            steps = K.equity_steps(s, p, ranges, tier_k, variant="c1")
            real = K.key(public, K.my_step(steps, s, p))
            hit = _row(policy, real, m) is not None
            kind = "call" if public.startswith("call|") else "other"
            by_street[str(s.street)]["decisions"] += 1
            by_street[str(s.street)]["hits"] += int(hit)
            kinds[kind]["decisions"] += 1
            kinds[kind]["hits"] += int(hit)
            for v, tab in cand.items():
                h = hit and visits.get(real, 0) >= int(v)
                for c in (tab["street"][str(s.street)], tab[kind]):
                    c["decisions"] += 1
                    c["hits"] += int(h)
            probs = np.empty((N, m))
            for v in np.unique(steps[steps >= 0]):
                row = _row(policy, K.key(public, int(v)), m)
                probs[steps == v] = row if row is not None else np.full(m, 1.0 / m)
            real_row = _row(policy, real, m)
            pr = np.asarray(real_row if real_row is not None else np.full(m, 1.0 / m), dtype=float)
            i = int(rng.choice(m, p=pr / pr.sum()))
            ranges = K.update_range(ranges, p, probs[:, i])
            s = G.apply(s, acts[i])
    out = {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, "players": players, "hands": hands, "seed": seed,
           "by_street": {k: _rate(c) for k, c in by_street.items()},
           "by_kind": {k: _rate(c) for k, c in kinds.items()}}
    if visits is not None:
        out["by_min_visits"] = {v: {"by_street": {k: _rate(c) for k, c in t["street"].items()},
                                    "by_kind": {k: _rate(t[k]) for k in ("call", "other")}} for v, t in cand.items()}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("policy", type=Path, help="web/app/policy/<tier>-<n>.json")
    ap.add_argument("--hands", type=int, default=200)
    ap.add_argument("--seed", type=int, default=611)
    ap.add_argument("--pod-result", type=Path, help="the training result holding the visit counts (min_visits table)")
    a = ap.parse_args(argv)
    policy, doc = load_policy(a.policy)
    if doc.get("key_variant", "c1") != "c1" and "|n" not in next(iter(policy), ""):
        raise SystemExit(f"{a.policy}: not a c1 table; this tool reads c1 keys only")
    visits = None
    if a.pod_result:
        from stalker.tools import export_web_policy as X

        st, _ = X.load_pod_result(a.pod_result)
        visits = dict(X.load_model(st).visits)
    res = measure(policy, doc["players"], doc["k"], doc["depth"], a.hands, a.seed, visits)
    json.dump({**res, "file": a.policy.name}, sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
