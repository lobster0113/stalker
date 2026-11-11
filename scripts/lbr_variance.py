"""LBR variance reduction, local measurement (#770): the plain LBR estimator next to an AIVAT-style corrected one.

    python scripts/lbr_variance.py --policy web/app/policy/mid-2.json --players 2 --hands 2000 --seeds 4 \
        [--samples 32] [--workers 4] [--out lbr-variance.json]

Each hand replays `referee.e3.lbr.lbr` exactly (same helpers, same rng draws, read-only import), so the plain
column is the referee's number for that seat and seed. The corrected column subtracts, from the LBR seat's payoff,
zero-mean terms built from a value function V (check-down value: mean `G.payoff` over board completions drawn from the
cards still in the deck, by a separate rng so the plain stream does not move):
  * hole deal:        V(dealt state) - mean V over freshly dealt holes and boards
  * policy seat acts: V(after the sampled action) - sum_a p(a) V(after a)   (p = the row the seat sampled from)
  * board cards:      V(after the cards) - V(before them, completions from the old board)
Undealt cards never steer any decision (the policy reads public state and its own hole; LBR reads `s.board`), so the
deck can be treated as dealt lazily and every term has conditional mean zero: the corrected mean is unbiased, the
difference is only variance. Seeds follow `stalker.tools.web_policy_lbr_job` (eval seed 10000+i, seat q at +101q).
A local reference number ("참고용"); CI numbers are the ones that count.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from referee.e3.lbr import Extra, _step, _value, extra_actions, seat_probs
from stalker.e2.eq_view import COMBO_ARR, combo_index
from stalker.e3 import game as G
from stalker.e3 import tp_key as K

SCHEMA = "stalker.research.lbr-variance"
AUX_SALT = 770   # the aux rng is seeded apart from the referee's stream


def _completions(aux: np.random.Generator, cards: tuple[int, ...], need: int, m: int) -> list[tuple[int, ...]]:
    if need == 0:
        return [()]
    pool = np.array(cards)
    return [tuple(int(c) for c in aux.choice(pool, size=need, replace=False)) for _ in range(m)]


def _checkdown(s: G.State, me: int, board: tuple[int, ...], comps) -> float:
    """V: the LBR seat's mean payoff (bb) if the hand ended now and went to showdown on `board` + each completion."""
    if s.done and len(s.live()) == 1:
        return float(G.payoff(s)[me]) / G.BB
    vals = [G.payoff(s._replace(board=board + c, done=True))[me] for c in comps]
    return float(np.mean(vals)) / G.BB


def _v_after(s: G.State, ns: G.State, me: int, comps) -> float:
    """V of the successor `ns` before any card it dealt is seen: completions from `s`'s board (same draws for every action)."""
    if ns.done and len(ns.live()) == 1:
        return float(G.payoff(ns)[me]) / G.BB
    if len(ns.board) == len(s.board) and ns.done:   # river showdown: nothing left to deal
        return float(G.payoff(ns)[me]) / G.BB
    return _checkdown(ns, me, s.board, comps)


def _v_now(ns: G.State, me: int, aux: np.random.Generator, m: int) -> float:
    """V of `ns` with the cards it holds: completions from its own board and deck."""
    if ns.done:
        return float(G.payoff(ns)[me]) / G.BB
    return _checkdown(ns, me, ns.board, _completions(aux, ns.deck, 5 - len(ns.board), m))


def _deal_baseline(s: G.State, me: int, aux: np.random.Generator, m: int) -> float:
    """Unbiased estimate of E over deals of V(dealt state): fresh holes and a full board for every draw."""
    vals = []
    for _ in range(m):
        d = [int(c) for c in aux.permutation(52)]
        hole = tuple((d[2 * i], d[2 * i + 1]) for i in range(s.n))
        board = tuple(d[2 * s.n:2 * s.n + 5])
        vals.append(G.payoff(s._replace(hole=hole, board=board, done=True))[me])
    return float(np.mean(vals)) / G.BB


def lbr_hands(policy, seat: int, hands: int, seed: int, k: int, n: int, depth: str = "full",
              extra_sizes: bool = False, samples: int = 32) -> tuple[list[float], list[float]]:
    """Per hand: (plain payoff, corrected payoff) in bb for the LBR seat. The loop is `referee.e3.lbr.lbr` line for line."""
    rng = np.random.default_rng(seed)
    aux = np.random.default_rng([seed, seat, AUX_SALT])
    plain, corr = [], []
    for _ in range(hands):
        s = G.deal(rng, n)
        mine = np.isin(COMBO_ARR, list(s.hole[seat])).any(axis=1)
        ranges = K.initial_ranges(n)
        c = _v_now(s, seat, aux, samples) - _deal_baseline(s, seat, aux, samples)
        while not s.done:
            p = s.to_act
            probs = seat_probs(policy, s, p, ranges, k, depth)
            acts = G.legal(s)
            if p != seat:
                row = probs[combo_index(s.hole[p])]
                a = int(rng.choice(len(acts), p=row / row.sum()))
            else:
                cands = acts + (extra_actions(s) if extra_sizes else [])
                vals = [_value(policy, s, x, ranges, mine, seat, k, depth) for x in cands]
                a = int(np.argmax(vals))
            chosen = cands[a] if p == seat else acts[a]
            comps = _completions(aux, s.deck, 5 - len(s.board), samples)
            ns = _step(s, chosen)
            if p != seat:   # action term: what the sampled action added beyond its expectation under the row
                q = row / row.sum()
                exp = sum(float(q[i]) * _v_after(s, _step(s, x), seat, comps) for i, x in enumerate(acts) if q[i] > 0)
                c += _v_after(s, ns, seat, comps) - exp
            if len(ns.board) > len(s.board):   # chance term: the cards this step dealt
                c += _v_now(ns, seat, aux, samples) - _v_after(s, ns, seat, comps)
            if isinstance(chosen, Extra):
                a = acts.index(chosen.menu) if chosen.menu in acts else acts.index("a")
            ranges = list(ranges)
            ranges[p] = ranges[p] * probs[:, a]
            s = ns
        win = float(G.payoff(s)[seat]) / G.BB
        plain.append(win)
        corr.append(win - c)
    return plain, corr


def _one(task: dict) -> dict:
    from stalker.tools import web_hit_rate as H
    from stalker.tools.web_policy_lbr import WebPolicy

    table, doc = H.load_policy(Path(task["policy"]))
    variant = H.variant_of(table, doc)
    pol = WebPolicy(table, doc["k"], task["backoff"])
    rules = H.rules_of(doc)
    with G.rules(rules["menu"], rules["raise_cap"]), K.using_variant(variant):
        plain, corr = lbr_hands(pol, task["seat"], task["hands"], task["eval_seed"] + 101 * task["seat"], doc["k"],
                                task["players"], doc["depth"], samples=task["samples"])
    return {**task, "plain": plain, "corrected": corr}


def _sd(x) -> float:
    return float(np.std(x, ddof=1)) if len(x) > 1 else 0.0


def summarize(rows: list[dict], players: int) -> dict:
    seeds = sorted({r["seed"] for r in rows})
    per_seed = []
    for sd in seeds:
        r = [x for x in rows if x["seed"] == sd]
        # the referee's lbr_bb: mean over seats of each seat's mean
        per_seed.append({"seed": sd, "plain_bb": round(float(np.mean([np.mean(x["plain"]) for x in r])), 4),
                         "corrected_bb": round(float(np.mean([np.mean(x["corrected"]) for x in r])), 4)})
    p = [x["plain_bb"] for x in per_seed]
    c = [x["corrected_bb"] for x in per_seed]
    hp = np.concatenate([x["plain"] for x in rows])
    hc = np.concatenate([x["corrected"] for x in rows])
    diff = hp - hc
    return {"players": players, "seeds": per_seed,
            "seed_sd": {"plain": round(_sd(p), 4), "corrected": round(_sd(c), 4),
                        "ratio": round(_sd(c) / _sd(p), 4) if _sd(p) > 0 else None},
            "hand_sd": {"plain": round(_sd(hp), 4), "corrected": round(_sd(hc), 4),
                        "ratio": round(_sd(hc) / _sd(hp), 4) if _sd(hp) > 0 else None},
            "mean": {"plain": round(float(hp.mean()), 4), "corrected": round(float(hc.mean()), 4),
                     "diff": round(float(diff.mean()), 4), "diff_stderr": round(_sd(diff) / np.sqrt(len(diff)), 4)}}


def run(policy: Path, players: int, hands: int, seeds: int, samples: int = 32, workers: int = 1,
        backoff: bool = False) -> dict:
    tasks = [{"policy": str(policy), "players": players, "hands": hands, "seed": i, "eval_seed": 10_000 + i,
              "seat": q, "samples": samples, "backoff": backoff} for i in range(1, seeds + 1) for q in range(players)]
    if workers > 1:
        with ProcessPoolExecutor(workers) as ex:
            rows = list(ex.map(_one, tasks))
    else:
        rows = [_one(t) for t in tasks]
    return {"schema": SCHEMA, "policy": Path(policy).name, "hands": hands, "samples": samples, "backoff": backoff,
            **summarize(rows, players)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--policy", type=Path, required=True)
    ap.add_argument("--players", type=int, required=True)
    ap.add_argument("--hands", type=int, default=2000, help="LBR hands per seat (ADR 0020: 2000 for 2 players)")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--samples", type=int, default=32, help="board completions per value estimate")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--backoff", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    res = run(a.policy, a.players, a.hands, a.seeds, a.samples, a.workers, a.backoff)
    text = json.dumps(res, indent=1, sort_keys=True) + "\n"
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
