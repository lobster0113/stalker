"""Hand-engine throughput benchmark: `python -m stalker.tools.bench_engine [--players 9] [--seconds 5]`.

Plays random legal hands (fold 20% when facing a bet, raise 25% when legal with a uniform size, else
check/call) on one core and prints hands/s for the PokerKit `Hand` and `FastHand`, plus the speedup.
Stacks are 100 BB with a BB ante, the most common MTT structure. Results are local reference numbers.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np

from stalker.tournament.fast_hand import FastHand
from stalker.tournament.hand import Hand

ENGINES = {"pokerkit": Hand, "fast": FastHand}


def play_random(hand, rng: np.random.Generator) -> int:
    n_actions = 0
    while not hand.is_over:
        la = hand.legal_actions()
        r = rng.random()
        if la.can_fold and r < 0.2:
            hand.fold()
        elif la.min_raise_to is not None and r > 0.75:
            hand.raise_to(int(rng.integers(la.min_raise_to, la.max_raise_to + 1)))
        else:
            hand.check_or_call()
        n_actions += 1
    return n_actions


def bench(engine: str, players: int, seconds: float, seed: int = 0) -> dict:
    cls = ENGINES[engine]
    rng = np.random.default_rng(seed)
    stacks = [200] * players
    hands = actions = 0
    start = time.perf_counter()
    deadline = start + seconds
    while True:
        for _ in range(50):
            h = cls(stacks, hands % players, 1, 2, rng, ante=2, ante_mode="bb_ante")
            actions += play_random(h, rng)
            h.result()
            hands += 1
        if time.perf_counter() >= deadline:
            break
    elapsed = time.perf_counter() - start
    return {"engine": engine, "players": players, "hands": hands, "seconds": round(elapsed, 3),
            "hands_per_s": round(hands / elapsed, 1), "actions_per_hand": round(actions / hands, 2)}


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--players", type=int, default=9)
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    rows = [bench(e, args.players, args.seconds, args.seed) for e in ENGINES]
    out = {"rows": rows, "speedup": round(rows[1]["hands_per_s"] / rows[0]["hands_per_s"], 1)}
    print(json.dumps(out))
    return out


if __name__ == "__main__":
    main()
