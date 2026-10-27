"""Differential test of `FastHand` against the PokerKit `Hand` (Gate R oracle).

`python -m stalker.tools.diff_engine --hands 100000 [--workers 4] [--seed 0]`

Each hand draws a random table (2..10 seats, empty seats, stack scales from sub-ante to deep, all ante
modes, odd blind ratios) and one seed; both engines deal from that seed, the same random action
sequence is applied to both, and every step must agree on the actor and the full legal-action set
(fold allowed, call amount, min/max raise-to). At the end hole cards, board and the whole `HandResult`
(stacks, pots, eligibility, per-pot awards) must be equal. Raise sizes are biased to min and all-in so
short all-ins, side pots and split pots occur often. Exit code 1 with the first mismatches on failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from stalker.tournament.fast_hand import FastHand
from stalker.tournament.hand import Hand


def random_spec(rng: np.random.Generator) -> dict:
    n_seats = int(rng.integers(2, 11))
    top = int(rng.choice([5, 30, 400, 5000]))
    stacks = [int(rng.integers(1, top + 1)) if rng.random() < 0.8 else 0 for _ in range(n_seats)]
    while sum(s > 0 for s in stacks) < 2:
        stacks[int(rng.integers(n_seats))] = int(rng.integers(1, top + 1))
    button = int(rng.choice([i for i, s in enumerate(stacks) if s > 0]))
    mode = str(rng.choice(["none", "classic", "bb_ante"]))
    ante = 0 if mode == "none" else int(rng.integers(1, 6))
    sb = int(rng.integers(1, 6))
    bb = sb * int(rng.integers(1, 3)) + int(rng.integers(0, 2))
    return dict(stacks=stacks, button=button, small_blind=sb, big_blind=bb, ante=ante, ante_mode=mode)


def compare_hand(spec: dict, deal_seed: int, rng: np.random.Generator) -> str | None:
    """Play one hand on both engines; return a mismatch description or None."""
    ref = Hand(rng=np.random.default_rng(deal_seed), **spec)
    fast = FastHand(rng=np.random.default_rng(deal_seed), **spec)
    for seat in ref.seats:
        shown = ref.hole_cards(seat)
        if shown != fast.hole_cards(seat):
            return f"hole cards seat {seat}: {shown} vs {fast.hole_cards(seat)}"
    while True:
        if ref.is_over != fast.is_over or ref.actor != fast.actor:
            return f"state after {ref.actions()}: over {ref.is_over}/{fast.is_over} actor {ref.actor}/{fast.actor}"
        if ref.is_over:
            break
        la = ref.legal_actions()
        lb = fast.legal_actions()
        if la != lb:
            return f"legal actions after {ref.actions()}: {la} vs {lb}"
        r = rng.random()
        if la.can_fold and r < 0.25:
            ref.fold()
            fast.fold()
        elif la.min_raise_to is not None and r > 0.6:
            x = rng.random()
            if x < 0.35:
                amount = la.max_raise_to
            elif x < 0.6:
                amount = la.min_raise_to
            else:
                amount = int(rng.integers(la.min_raise_to, la.max_raise_to + 1))
            ref.raise_to(amount)
            fast.raise_to(amount)
        else:
            ref.check_or_call()
            fast.check_or_call()
    if ref.board() != fast.board():
        return f"board {ref.board()} vs {fast.board()}"
    if ref.result() != fast.result():
        return f"result after {ref.actions()}: {ref.result()} vs {fast.result()}"
    return None


def run_chunk(seed: int, hands: int, max_failures: int = 5) -> dict:
    rng = np.random.default_rng(seed)
    failures = []
    for k in range(hands):
        spec = random_spec(rng)
        deal_seed = int(rng.integers(2**63))
        msg = compare_hand(spec, deal_seed, rng)
        if msg is not None:
            failures.append({"chunk_seed": seed, "hand": k, "spec": spec, "deal_seed": deal_seed, "msg": msg})
            if len(failures) >= max_failures:
                break
    return {"hands": hands, "failures": failures}


def run(hands: int, seed: int = 0, workers: int = 1, chunk: int = 2000) -> dict:
    """Compare `hands` hands split into seeded chunks (results do not depend on `workers`)."""
    sizes = [chunk] * (hands // chunk) + ([hands % chunk] if hands % chunk else [])
    seeds = [seed * 1_000_003 + i for i in range(len(sizes))]
    if workers > 1:
        with ProcessPoolExecutor(workers) as ex:
            parts = list(ex.map(run_chunk, seeds, sizes))
    else:
        parts = [run_chunk(s, n) for s, n in zip(seeds, sizes)]
    failures = [f for p in parts for f in p["failures"]]
    return {"hands": hands, "seed": seed, "mismatches": len(failures), "failures": failures[:5]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FastHand vs PokerKit differential test")
    ap.add_argument("--hands", type=int, default=100_000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args(argv)
    out = run(args.hands, args.seed, args.workers)
    print(json.dumps(out, default=str))
    return 1 if out["mismatches"] else 0


if __name__ == "__main__":
    sys.exit(main())
