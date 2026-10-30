"""Range-policy fixed point (#411): which ranges should TP features be read from while training?

A TP key reads hand.equity against the opponent's public range, and that range moves with the policy
being trained, so a (public history, hole cards) state can move between keys from one iteration to the
next. Four designs, each on games where the exact best response is cheap:

    A     current-strategy ranges (every iteration; stalker/e3/mccfr.py ranges="current")
    B<k>  average-strategy ranges, refreshed every k iterations (ranges="average", range_every=k)
    C<E>  the current strategy's ranges, snapshotted at an epoch boundary and frozen for E iterations
          (A is C1; a frozen *average* snapshot is B<E>, so B100 is the long-epoch average arm)
    D     policy-independent ranges: the subgame's starting ranges (a fixed bucketing of hands)

Metrics per arm: `key_churn_rate` (share of (decision node, private state) pairs whose key changed
since the previous refresh), the exploitability curve of the deployed average policy, its head-to-head
EV against the per-combo solution of the same game, and the time per iteration. The deployed policy
reads its keys from its own public ranges (the info contract, docs/TP.md section 2), except D, which
by design reads the fixed ranges; D is also reported under its own ranges (`expl_policy_keys`).

Seeds pick the game (river: the board; Leduc: the players' priors over ranks), so every arm runs on
the same deals. The solver is deterministic: the spread across seeds is the spread across games.

    python -m stalker.vcfr.fixed_point --games river-small leduc --iters 300 --seeds 1 2 3 4
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np

from stalker.vcfr import solver as S
from stalker.vcfr.leduc import LeducGame, random_priors
from stalker.vcfr.river import REAL_BETS, REAL_RAISES, RiverGame

# name -> (solver key_ranges, refresh period)
ARMS = {"A": ("current", 1), "B10": ("average", 10), "B100": ("average", 100),
        "C10": ("snapshot", 10), "C100": ("snapshot", 100), "D": ("initial", 1)}
RIVER_K = 17          # the pro tier's hand.equity steps (stalker/e3/tp_key.py TIER_K)
# Leduc has three ranks, whose equity order against any range is fixed, so a quantile scale never moves
# a rank between keys; equity thirds do, which is the range sensitivity this experiment is about.
LEDUC_K = 3
GAMES = ("river-tiny", "river-small", "river-real", "leduc")
# Two-sided 95% t quantiles by degrees of freedom: seeds are few, the normal 1.96 would be too narrow.
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}


def river_board(seed: int) -> tuple[int, ...]:
    return tuple(int(c) for c in np.random.default_rng(seed).choice(52, 5, replace=False))


def make_game(name: str, seed: int):
    """(game, keyer) for one game and seed."""
    if name == "leduc":
        return LeducGame(random_priors(seed)), S.tp_keyer(LEDUC_K, scale="abs")
    menus = {"river-tiny": dict(stack=1.0, bets=(1.0,), raises=(), raise_cap=2),
             "river-small": {},
             "river-real": dict(bets=REAL_BETS, raises=REAL_RAISES, raise_cap=3)}
    if name not in menus:
        raise ValueError(f"game {name!r}; use one of {GAMES}")
    return RiverGame(river_board(seed), **menus[name]), S.tp_keyer(RIVER_K)


def checkpoints(iters: int) -> list[int]:
    pts = {x for x in (10, 30, 100, 300, 1000, 3000, 10000, 30000) if x < iters}
    return sorted(pts | {iters})


def _flat(game, rows: dict[int, np.ndarray]) -> np.ndarray:
    return np.concatenate([rows[nd.id] for nd in game.decision_nodes()])


def current_keys(m: S.VectorCFR) -> np.ndarray:
    """Keys of every (node, private state) under the current strategy's own ranges."""
    out: dict[int, np.ndarray] = {}
    m.materialize(average=False, keys_out=out)
    return _flat(m.game, out)


def training_keys(m: S.VectorCFR) -> np.ndarray:
    """Keys the next iteration reads (stored snapshot, or the fixed ranges)."""
    return _flat(m.game, {nd.id: m._rows(nd, None, None)[1] for nd in m.game.decision_nodes()})


def run_arm(game, keyer, arm: str, iters: int, ref: dict | None) -> dict:
    kr, refresh = ARMS[arm]
    m = S.VectorCFR(game, keyer, kr, refresh)
    pot = getattr(game, "pot", 1.0)
    pts = checkpoints(iters)
    churn: list[tuple[int, float]] = []          # (iteration, share changed since the previous refresh)
    prev = None
    curve, train = {}, 0.0
    seen = 0
    for it in range(1, iters + 1):
        if kr == "current":
            keys = current_keys(m)              # the keys this iteration reads
            if prev is not None:
                churn.append((it, float(np.mean(keys != prev))))
            prev = keys
        t0 = time.perf_counter()
        m.iterate(1)
        train += time.perf_counter() - t0
        if kr in ("average", "snapshot") and m.refreshes > seen:
            seen = m.refreshes
            keys = training_keys(m)
            if prev is not None:
                churn.append((it, float(np.mean(keys != prev))))
            prev = keys
        if it in pts:
            if kr == "initial":                 # measured, not assumed: compare with the last checkpoint
                keys = training_keys(m)
                if prev is not None:
                    churn.append((it, float(np.mean(keys != prev))))
                prev = keys
            deploy = m.materialize(keys="train" if kr == "initial" else "policy")
            curve[it] = round(100 * S.exploitability(game, deploy) / pot, 4)
    deploy = m.materialize(keys="train" if kr == "initial" else "policy")
    rates = [c for _, c in churn]
    q = max(1, len(rates) // 4)
    windows, lo = {}, 0
    for p in pts:                               # mean churn per refresh in each checkpoint window
        w = [c for i, c in churn if lo < i <= p]
        windows[p] = round(float(np.mean(w)), 5) if w else None
        lo = p
    out = {"arm": arm, "key_ranges": kr, "refresh": refresh, "rows": int(sum(v.shape[0] for v in m.regret.values())),
           "expl_pct_pot": curve, "expl_final": curve[iters],
           "ms_per_iter": round(1000 * train / iters, 3), "refreshes": len(rates),
           "churn_early": round(float(np.mean(rates[:3])), 5) if rates else 0.0,
           "churn_late": round(float(np.mean(rates[-q:])), 5) if rates else 0.0,
           "churn_by_window": windows}
    if kr == "initial":
        out["expl_policy_keys"] = round(100 * S.exploitability(game, m.materialize(keys="policy")) / pot, 4)
    if ref is not None:
        out["h2h_vs_combo_pct_pot"] = round(100 * S.head_to_head(game, deploy, ref) / pot, 4)
    return out


def run_seed(seed: int, games=("river-small", "leduc"), iters: int = 300, arms=tuple(ARMS)) -> dict:
    out = {"seed": seed, "iters": iters, "games": {}}
    for name in games:
        game, keyer = make_game(name, seed)
        combo = S.VectorCFR(game)
        t0 = time.perf_counter()
        combo.iterate(iters)
        ref = combo.materialize()
        pot = getattr(game, "pot", 1.0)
        g = {"decision_nodes": len(game.decision_nodes()), "private_states": game.sd.n,
             "combo": {"expl_final": round(100 * S.exploitability(game, ref) / pot, 4),
                       "ms_per_iter": round(1000 * (time.perf_counter() - t0) / iters, 3)},
             "arms": {a: run_arm(game, keyer, a, iters, ref) for a in arms}}
        if name.startswith("river"):
            g["board"] = list(river_board(seed))
        out["games"][name] = g
    return out


def _ci(xs: list[float]) -> dict:
    a = np.asarray(xs, dtype=float)
    n = len(a)
    half = float(T95.get(n - 1, 1.96) * a.std(ddof=1) / np.sqrt(n)) if n > 1 else None
    return {"mean": round(float(a.mean()), 4), "ci95": None if half is None else round(half, 4), "n": n}


def aggregate(runs: list[dict]) -> dict:
    """Means and 95% t intervals over seeds, and paired differences against arm A (same games)."""
    out: dict = {"seeds": [r["seed"] for r in runs], "iters": runs[0]["iters"], "games": {}}
    for name in runs[0]["games"]:
        per = [r["games"][name] for r in runs]
        g: dict = {"combo_expl_final": _ci([p["combo"]["expl_final"] for p in per]), "arms": {}}
        for arm in per[0]["arms"]:
            rows = [p["arms"][arm] for p in per]
            a: dict = {}
            for k in ("expl_final", "h2h_vs_combo_pct_pot", "ms_per_iter", "churn_early", "churn_late",
                      "expl_policy_keys"):
                if all(k in x for x in rows):
                    a[k] = _ci([x[k] for x in rows])
            a["expl_curve"] = {it: _ci([x["expl_pct_pot"][it] for x in rows]) for it in rows[0]["expl_pct_pot"]}
            a["churn_by_window"] = {w: _ci([x["churn_by_window"][w] for x in rows])
                                    for w in rows[0]["churn_by_window"] if all(x["churn_by_window"][w] is not None
                                                                               for x in rows)}
            if arm != "A" and "A" in per[0]["arms"]:
                for k in ("expl_final", "h2h_vs_combo_pct_pot"):
                    if all(k in x for x in rows):
                        a[f"{k}_minus_A"] = _ci([x[k] - p["arms"]["A"][k] for x, p in zip(rows, per)])
            g["arms"][arm] = a
        out["games"][name] = g
    return out


def _fmt(c: dict | None) -> str:
    if c is None:
        return "-"
    return f"{c['mean']:.3f}" + ("" if c["ci95"] is None else f" +- {c['ci95']:.3f}")


def table(agg: dict) -> str:
    """Markdown: one row per (game, arm)."""
    lines = ["| game | arm | expl % pot (final) | expl - A (paired) | h2h vs combo % pot | churn early | churn late "
             "| ms/iter |", "|---|---|---|---|---|---|---|---|"]
    for name, g in agg["games"].items():
        lines.append(f"| {name} | combo | {_fmt(g['combo_expl_final'])} | - | 0 | - | - | - |")
        for arm, a in g["arms"].items():
            expl = _fmt(a["expl_final"]) + (f" (own ranges {_fmt(a['expl_policy_keys'])})" if "expl_policy_keys" in a else "")
            lines.append(f"| {name} | {arm} | {expl} | {_fmt(a.get('expl_final_minus_A'))} | "
                         f"{_fmt(a.get('h2h_vs_combo_pct_pot'))} | {_fmt(a['churn_early'])} | {_fmt(a['churn_late'])} | "
                         f"{_fmt(a['ms_per_iter'])} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Range-policy fixed point arms A-D (#411)")
    ap.add_argument("--games", nargs="+", choices=GAMES, default=["river-small", "leduc"])
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4])
    ap.add_argument("--arms", nargs="+", choices=list(ARMS), default=list(ARMS))
    ap.add_argument("--out", help="write per-seed results and the aggregate as JSON here")
    a = ap.parse_args(argv)
    runs = [run_seed(s, a.games, a.iters, a.arms) for s in a.seeds]
    agg = aggregate(runs)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"runs": runs, "aggregate": agg}, f, indent=1)
    print(table(agg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
