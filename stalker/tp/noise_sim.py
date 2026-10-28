"""Decision loss of a noisy TP learner, by question form and level (#261, #216-1).

Trains the E2 beginner policy for each form — A: equity against the opponent's range
(`stalker.e2.eq_view`), B: hand rank (`hand.pct`, the `beginner` tier of `stalker.e2.tiers`) — then
plays a learner who feeds that same policy a noisy chip (`noise_learner`) against the same policy
fed the true chip. Loss = what the noisy seat gives up versus playing the same deal with true chips,
bb/hand; seats alternate, so every deal is played from both positions over the run. No LBR is used (#259).

Both seats' public ranges (form A) are always updated from the TRUE-chip strategy: the learner's
model of the opponent stays exact, only the reading of their own hand is noisy.

    python -m stalker.tp.noise_sim --iters 3000 --hands 400 --seed 1
"""
from __future__ import annotations

import argparse
import json
import sys
from functools import lru_cache

import numpy as np

from stalker.core.cards import COMBOS
from stalker.e2 import game as G
from stalker.e2.abstraction import TIERS, _combo_classes, ehs_table
from stalker.e2.eq_view import EQ_TIERS, EqMCCFR, combo_index, equity_vs, eq_buckets, seat_probs
from stalker.e2.mccfr import MCCFR
from stalker.tp.noise_learner import LEVELS, Level, chip_equity_form, chip_pct_form

N = len(COMBOS)
FORMS = ("equity", "pct")
K = EQ_TIERS["beginner"]


@lru_cache(maxsize=1)
def _preflop_stat() -> np.ndarray:
    from referee.anchors.hu_equity import load

    E, Np = load()
    return ((Np * E).sum(axis=1) / Np.sum(axis=1))[_combo_classes()]


def pct_stat(board: tuple[int, ...]) -> np.ndarray:
    """Strength statistic behind `hand.pct` (the abstraction's own: vs-random preflop, EHS postflop)."""
    return _preflop_stat() if not board else ehs_table(tuple(board))


def train(form: str, iters: int, seed: int) -> dict[str, list[float]]:
    m = EqMCCFR(seed, K) if form == "equity" else MCCFR(seed, TIERS["beginner"])
    m.iterate(iters)
    return m.policy()


def _hist(s: G.State) -> str:
    return "".join(h if len(h) == 1 else h[1:] for h in s.history)


def _bucket(form: str, s: G.State, seat: int, ranges, level: Level | None, rng) -> tuple[int, np.ndarray | None]:
    """The chip the seat feeds the policy (true when level is None) and, for form A, all combos' true chips."""
    hole = combo_index(s.hole[seat])
    if form == "equity":
        true_b = eq_buckets(s.board, ranges[1 - seat], K)
        if level is None:
            return int(true_b[hole]), true_b
        return chip_equity_form(equity_vs(tuple(s.board), ranges[1 - seat]), hole, K, level, rng), true_b
    if level is None:
        return int(TIERS["beginner"].combo_buckets(tuple(s.board))[hole]), None
    return chip_pct_form(pct_stat(tuple(s.board)), hole, K, level, rng), None


def play_hand(form: str, policy, deal: G.State, noisy_seat: int, level: Level | None, seed: tuple) -> float:
    """bb won by the noisy seat. Action draws come from one stream per (hand, seat), noise from another, so
    a learner with no noise reproduces the true-chip play exactly."""
    act_rng = [np.random.default_rng([*seed, 0, 0]), np.random.default_rng([*seed, 0, 1])]
    noise_rng = np.random.default_rng([*seed, 1])
    ranges = (np.ones(N), np.ones(N))
    s = deal
    while not s.done:
        p = s.to_act
        acts = G.legal(s)
        lv = level if p == noisy_seat else None
        b, true_b = _bucket(form, s, p, ranges, lv, noise_rng)
        probs = policy.get(f"{p}|{s.street}|{b}|{_hist(s)}")
        probs = np.full(len(acts), 1.0 / len(acts)) if probs is None or len(probs) != len(acts) else np.asarray(probs)
        a = int(act_rng[p].choice(len(acts), p=probs / probs.sum()))
        if true_b is not None:  # form A: the public range follows the seat's TRUE-chip strategy
            sp = seat_probs(lambda k_: policy.get(k_), s, p, true_b, len(acts))
            r = list(ranges)
            r[p] = ranges[p] * sp[:, a]
            ranges = (r[0], r[1])
        s = G.apply(s, acts[a])
    v = G.payoff(s) / G.BB
    return v if noisy_seat == 0 else -v


def loss(form: str, policy, level_name: str, hands: int, seed: int) -> dict:
    """Mean bb/hand the noisy learner loses against the true-chip play of the same policy, with 95% CI."""
    level = LEVELS[level_name]
    deal_rng = np.random.default_rng([seed, 99])
    diff = []
    for h in range(hands):
        deal = G.deal(deal_rng)
        base = play_hand(form, policy, deal, h % 2, None, (seed, h))  # same deal and draws, true chips both sides
        diff.append(base - play_hand(form, policy, deal, h % 2, level, (seed, h)))
    diff = np.array(diff)
    se = float(diff.std(ddof=1) / np.sqrt(hands)) if hands > 1 else 0.0
    return {"form": form, "level": level_name, "hands": hands, "loss_bb": round(float(diff.mean()), 4),
            "ci95_bb": round(1.96 * se, 4)}


def table(iters: int, hands: int, seed: int, levels=("expert", "mid", "beginner"), forms=FORMS) -> list[dict]:
    rows = []
    for form in forms:
        policy = train(form, iters, seed)
        for lv in levels:
            rows.append({"iters": iters, "seed": seed, **loss(form, policy, lv, hands, seed * 1000 + 7)})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--iters", type=int, default=3000)
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--levels", nargs="+", choices=sorted(LEVELS), default=["expert", "mid", "beginner"])
    ap.add_argument("--forms", nargs="+", choices=FORMS, default=list(FORMS))
    a = ap.parse_args(argv)
    for row in table(a.iters, a.hands, a.seed, a.levels, a.forms):
        print(json.dumps(row), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
