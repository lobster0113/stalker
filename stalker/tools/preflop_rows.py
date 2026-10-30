"""Served-policy rows for first-in preflop spots (#391): `python -m stalker.tools.preflop_rows --policy mid-6.json`.

For every seat that can be first in (everyone before it folded), prints the policy row of each
hand.equity step of that spot's key, with the step a given hand (`--hand`, default AhQh) falls in marked
`*`. The folds move the public ranges as training and the page do: each folding seat's range times its
fold probability per combo, read from the same table (a missing key plays uniform, like the page). So
the steps match what the served policy sees, and a leak like "BTN never opens, mostly limps" shows as a
row.

`--policy` takes the web service's file (`web/app/policy/<tier>-6.json`, `stalker.web.policy`) or a CI
`<job>-seed<s>.policy.json` (`{"average", "current"}`; pick with `--strategy`, give `--tier`).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from stalker.core.cards import cards
from stalker.e2.eq_view import combo_index
from stalker.e3 import game as G
from stalker.e3 import tp_key as K


def load(path: Path, strategy: str = "current", tier: str | None = None, players: int = 6) -> dict:
    """{"policy": key -> probabilities, "k", "depth", "players", "menu", "raise_cap", "label"}."""
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("schema") == "stalker.web.policy":
        q = d["q"]
        pol = {k: [x / q for x in v] for k, v in d["policy"].items()}
        return {"policy": pol, "k": d["k"], "depth": d["depth"], "players": d["players"],
                "menu": d.get("menu", "v1"), "raise_cap": d.get("raise_cap", G.RAISE_CAP),
                "label": f"{d.get('tier')} {d.get('strategy')} run {d.get('run_id')} ({d.get('iterations')} it)"}
    if "average" in d and "current" in d:
        if tier is None:
            raise SystemExit(f"{path}: a CI policy file does not name its tier; pass --tier")
        return {"policy": d[strategy], "k": K.TIER_K[tier], "depth": K.TIER_DEPTH[tier], "players": players,
                "menu": "v1", "raise_cap": G.RAISE_CAP, "label": f"{tier} {strategy} {path.name}"}
    raise SystemExit(f"{path}: neither a web policy (stalker.web.policy) nor a CI .policy.json")


def _row(policy: dict, key: str, m: int) -> np.ndarray:
    r = policy.get(key)
    return np.full(m, 1.0 / m) if r is None or len(r) != m else np.asarray(r, dtype=float)


def first_in(t: dict, hand: str = "AhQh") -> list[dict]:
    """One entry per first-in seat: its position, legal actions, hand step and every step's row."""
    n, k, depth, pol = t["players"], t["k"], t["depth"], t["policy"]
    s = G.deal(np.random.default_rng(0), n, t["menu"], t["raise_cap"])  # preflop keys ignore the cards
    ranges = K.initial_ranges(n)
    combo = combo_index(tuple(cards(hand)))
    names = G.position_names(n)
    out = []
    for p in range(n - 1):  # the big blind is never first in
        acts = G.legal(s)
        steps = K.equity_steps(s, p, ranges, k)
        public = K.public_key(s, p, depth)
        rows = [(K.key(public, v), _row(pol, K.key(public, v), len(acts))) for v in range(k)]
        out.append({"seat": p, "position": names[p], "public": public, "actions": acts,
                    "hand_step": int(steps[combo]),
                    "rows": [{"step": v, "key": key, "probs": r.round(4).tolist(), "in_table": key in pol}
                             for v, (key, r) in enumerate(rows)]})
        fold = np.array([r[acts.index("f")] for _, r in rows])[np.maximum(steps, 0)]
        ranges = K.update_range(ranges, p, np.where(steps < 0, 0.0, fold))
        s = G.apply(s, "f")
    return out


def render(t: dict, spots: list[dict], hand: str) -> str:
    lines = [f"# {t['label']}: first-in preflop rows (hand {hand} marked *)"]
    for sp in spots:
        lines.append(f"\n{sp['position']} (seat {sp['seat']}) key {sp['public']}|e<step>, {hand} at e{sp['hand_step']}")
        lines.append("step  " + "  ".join(f"{a:>6}" for a in sp["actions"]))
        for r in sp["rows"]:
            mark = "*" if r["step"] == sp["hand_step"] else " "
            miss = "" if r["in_table"] else "  (not in table: uniform)"
            lines.append(f"{mark}e{r['step']:<3} " + "  ".join(f"{100 * p:5.1f}%" for p in r["probs"]) + miss)
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--policy", type=Path, required=True, action="append", help="repeat to print several tables")
    ap.add_argument("--strategy", choices=("current", "average"), default="current", help="for a CI .policy.json")
    ap.add_argument("--tier", choices=sorted(K.TIER_K), help="for a CI .policy.json")
    ap.add_argument("--players", type=int, default=6, help="for a CI .policy.json")
    ap.add_argument("--hand", default="AhQh")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(argv)
    for path in a.policy:
        t = load(path, a.strategy, a.tier, a.players)
        spots = first_in(t, a.hand)
        print(json.dumps({"label": t["label"], "spots": spots}) if a.json else render(t, spots, a.hand))
    return 0


if __name__ == "__main__":
    sys.exit(main())
