"""Train an unconstrained CFR+ policy on a toy game and log exact exploitability.

    python -m stalker.toy.train --game leduc --iters 2000 --every 100 --seed 1 --out runs/leduc.jsonl

Each JSONL line: {"game", "iteration", "exploitability", "game_value", "seed"}; the final strategy is
written next to it as <out>.strategy.json (with the seed). Full-traversal CFR+ uses no randomness, so
the seed does not change the result; it is recorded and passed on for sampled variants.
Values are local reference numbers; judged numbers come from CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from referee.anchors.toy import exploitability, expected_value, kuhn, leduc

from .cfr import train

GAMES = {"kuhn": kuhn.game, "leduc": leduc.game}


def run(game: str, iters: int, every: int, out: Path | None, seed: int = 0) -> list[dict]:
    if game not in GAMES:
        raise SystemExit(f"unknown game {game!r}; choose one of {sorted(GAMES)}")
    root = GAMES[game]()
    rows: list[dict] = []
    fh = out.open("w", encoding="utf-8") if out else None

    def log(it: int, strategy: dict) -> None:
        row = {"game": game, "iteration": it, "exploitability": exploitability(root, strategy),
               "game_value": expected_value(root, strategy), "seed": seed}
        rows.append(row)
        line = json.dumps(row)
        if fh:
            fh.write(line + "\n")
        else:
            print(line)

    try:
        strategy = train(root, iters, every, log, rng=np.random.default_rng(seed))
    finally:
        if fh:
            fh.close()
    if out:
        out.with_suffix(".strategy.json").write_text(json.dumps({"seed": seed, "strategy": strategy}, sort_keys=True),
                                                     encoding="utf-8")
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--game", required=True, choices=sorted(GAMES))
    ap.add_argument("--iters", type=int, default=1000)
    ap.add_argument("--every", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
    run(a.game, a.iters, a.every, a.out, a.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
