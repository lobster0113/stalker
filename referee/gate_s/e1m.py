"""Gate S v0 on E1m (#313): insensitivity on 3-handed ICM push/fold, judged against the exact reference.

The E1 gate (`referee.gate_s`) carried to the multiway reference `referee.anchors.icm_reference`
(BTN, SB, BB; blinds 50/100 chips; ICM payouts from the spot set). The anchor is unconstrained
fictitious play with tol=0 for a fixed number of iterations (`anchor_iters`), as the E1m research
baseline. A policy is `policy(spot) -> {decision: (probs, tp_bins)}` for the five decisions
("push", p) and ("call", q, p); `tp_bins` may be None. Optional `tp_step_points` as in E1.

A perturbation moves one seat's stack inside its `docs/TP.md` §6 bucket on the 1 BB grid. Every seat
staying in its bucket keeps every pairwise effective stack in its bucket too (min is monotone), and
positions and player count stay. Per decision, per hand, the anchor's EV advantage of the aggressive
action over folding against the anchor's other seats decides the role (stable / sensitivity
exception / neither), exactly as in E1. Weights: the class prior for a push, the reach mass for a
call. Values are prize-pool units; the pot converts at prize pool / total chips (ICM is close to
linear at these stacks): a push decision's pot is the posts, a call's the posts plus the matched
all-in. Metrics and pass rule are E1's (ADR 0016), aggregated over (pair, decision). Boundary
cliffs are not measured on E1m yet.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from referee.anchors import icm_reference as R
from referee.gate_s import SpotError, _wpct

SPOTS_E1M_V1 = Path(__file__).resolve().parent / "spots_e1m_v1.json"
DECISIONS = (("push", 0), ("push", 1), ("call", 1, 0), ("call", 2, 0), ("call", 2, 1))
SB, BB = 50, 100


def load(path: Path = SPOTS_E1M_V1) -> tuple[dict, str]:
    raw = path.read_bytes()
    spec = json.loads(raw)
    for key in ("version", "seed", "per_base", "payouts", "anchor_iters", "bucket_edges", "grid", "flip_margin_pot",
                "thresholds", "base", "golden"):
        if key not in spec:
            raise SpotError(f"{path.name}: missing {key!r}; regenerate with python -m referee.gate_s.make_spots_e1m")
    if len(spec["golden"]) < 5:
        raise SpotError(f"{path.name}: {len(spec['golden'])} golden spots; Gate S needs at least 5")
    for g in spec["golden"]:
        if bucket(g["base"][g["seat"]], spec["bucket_edges"]) != bucket(g["to"], spec["bucket_edges"]):
            raise SpotError(f"{path.name}: golden {g} crosses a bucket edge; golden spots are in-bucket")
    return spec, hashlib.sha256(raw).hexdigest()


def bucket(stack: float, edges) -> int:
    return next((i for i, e in enumerate(edges) if stack <= e), len(edges))


def spot(stacks_bb, payouts) -> R.Spot:
    return R.Spot(tuple(int(round(s * BB)) for s in stacks_bb), SB, BB, tuple(payouts))


def moves(spec: dict, base) -> list[tuple[int, float]]:
    """Every in-bucket (seat, new stack) for a base triple, on the spot set's grid."""
    edges = spec["bucket_edges"]
    return [(i, float(s)) for i in range(len(base)) for s in spec["grid"]
            if s != base[i] and bucket(s, edges) == bucket(base[i], edges)]


def pairs(spec: dict) -> list[tuple[tuple, tuple]]:
    """(base stacks, perturbed stacks): `per_base` seeded draws among each base's in-bucket moves."""
    rng = np.random.default_rng(spec["seed"])
    out = []
    for base in (tuple(float(x) for x in b) for b in spec["base"]):
        mv = moves(spec, base)
        for j in rng.choice(len(mv), size=min(spec["per_base"], len(mv)), replace=False):
            seat, s = mv[j]
            out.append((base, base[:seat] + (s,) + base[seat + 1:]))
    return out


@lru_cache(maxsize=None)
def _solve(stacks: tuple, payouts: tuple, iters: int):
    sp = spot(stacks, payouts)
    tree = R._Tree(sp, R._value_fn(sp, "icm", 0, R.BASELINE_TOL, iters))
    st = R._solve_tree(tree, R._scale(sp, "icm"), 0.0, iters).strategy
    return sp, tree, st, tree.evaluate(st)


def anchor(spec: dict, stacks) -> tuple[R.Spot, R.Strategy]:
    sp, _, st, _ = _solve(tuple(float(x) for x in stacks), tuple(spec["payouts"]), spec["anchor_iters"])
    return sp, st


@lru_cache(maxsize=None)
def _decision(stacks: tuple, payouts: tuple, iters: int, d: tuple):
    """(advantage per class in prize-pool units, normalised weights or None if unreached, pot)."""
    sp, _, _, ev = _solve(stacks, payouts, iters)
    to_pp = sp.prize_pool / float(sum(sp.stacks))
    if d[0] == "push":
        e, fold = ev.push_ev[d[1]]
        return e - fold, R.PRIOR, float(sp.posts.sum()) * to_pp
    q, p = d[1], d[2]
    e, fold, mass = ev.call_ev[q, p]
    behind = np.asarray(sp.stacks, dtype=float) - sp.dead
    pot = float(sp.posts.sum()) + min(behind[p], behind[q])
    return e - fold, (mass / mass.sum() if mass.sum() > 0 else None), pot * to_pp


def _dec(spec, stacks, d):
    return _decision(tuple(float(x) for x in stacks), tuple(spec["payouts"]), spec["anchor_iters"], d)


def loss_pct(spec: dict, stacks, d: tuple, probs: np.ndarray) -> float:
    """The policy's loss against the anchor's best action at one decision, per decision reached, % of the pot."""
    adv, w, pot = _dec(spec, stacks, d)
    return 100.0 * float((w * (np.maximum(adv, 0) - probs * adv)).sum()) / pot


def roles(spec: dict, a, b, d: tuple):
    """(stable mask, exception mask, direction +1/-1 of the anchor's move on exception hands)."""
    adv_a, _, pot_a = _dec(spec, a, d)
    adv_b, _, pot_b = _dec(spec, b, d)
    m = spec["flip_margin_pot"]
    best_a, best_b = adv_a > 0, adv_b > 0
    stable = best_a == best_b
    clear = (np.abs(adv_a) >= m * pot_a) & (np.abs(adv_b) >= m * pot_b)
    return stable, ~stable & clear, np.where(best_b, 1.0, -1.0)


def reached(spec, a, b, d) -> bool:
    return _dec(spec, a, d)[1] is not None and _dec(spec, b, d)[1] is not None


def evaluate(policy, spec: dict | None = None) -> dict:
    spec = spec or load()[0]
    th = spec["thresholds"]
    cache = {}

    def act(stacks):
        k = tuple(float(x) for x in stacks)
        if k not in cache:
            out = policy(spot(k, spec["payouts"]))
            for d in DECISIONS:
                probs = np.asarray(out[d][0], dtype=float)
                if probs.shape != (R.N_CLASSES,) or ((probs < 0) | (probs > 1)).any():
                    raise ValueError(f"policy must return 169 probabilities in [0, 1] for {d} (HAND_CLASSES order)")
            cache[k] = {d: (np.asarray(out[d][0], dtype=float), None if out[d][1] is None else np.asarray(out[d][1]))
                        for d in DECISIONS}
        return cache[k]

    step_pts = float(getattr(policy, "tp_step_points", 100.0))
    tv, tp, reg, tv_dec = [], [], [], []
    for a, b in pairs(spec):
        pa, pb = act(a), act(b)
        for d in DECISIONS:
            if not reached(spec, a, b, d):
                continue
            stable, _, _ = roles(spec, a, b, d)
            w = _dec(spec, a, d)[1]
            ws = w * stable
            tv.append(float((ws * np.abs(pa[d][0] - pb[d][0])).sum() / ws.sum()) if ws.sum() > 0 else 0.0)
            tv_dec.append(d[0])
            if pa[d][1] is not None:
                tp.append(_wpct(np.abs(pa[d][1] - pb[d][1]).astype(float), w, 95))
            reg.append(max(0.0, loss_pct(spec, b, d, pb[d][0]) - loss_pct(spec, a, d, pa[d][0])))
    golden = []
    for gs in spec["golden"]:
        a = tuple(float(x) for x in gs["base"])
        b = a[:gs["seat"]] + (float(gs["to"]),) + a[gs["seat"] + 1:]
        d = tuple(gs["decision"])
        _, exc, direction = roles(spec, a, b, d)
        w = _dec(spec, a, d)[1] * exc
        moved = float((w * np.maximum(0.0, direction * (act(b)[d][0] - act(a)[d][0]))).sum() / w.sum())
        golden.append({**gs, "moved": round(moved, 4), "ok": moved >= th["golden_moved"]})
    out = {"pairs": len(pairs(spec)), "decisions": len(tv), "tv_p95": round(float(np.percentile(tv, 95)), 4),
           "tv_p95_by_kind": {k: round(float(np.percentile([t for t, x in zip(tv, tv_dec) if x == k], 95)), 4)
                              for k in ("push", "call") if k in tv_dec},
           "tp_change_p95": None if not tp else round(float(np.percentile(tp, 95)), 3),
           "tp_change_p95_points": None if not tp else round(float(np.percentile(tp, 95)) * step_pts, 3),
           "stab_regret_mean_pct": round(float(np.mean(reg)), 4), "stab_regret_p99_pct": round(float(np.percentile(reg, 99)), 4),
           "golden": golden}
    fails = []
    if out["tv_p95"] > th["tv_p95"]:
        fails.append(f"tv p95 {out['tv_p95']} > {th['tv_p95']}: actions move inside a bucket where the anchor's best action does not")
    allowed = max(th["tp_change_steps"] * step_pts, th["tp_change_points"])
    if out["tp_change_p95"] is not None and out["tp_change_p95_points"] > allowed:
        fails.append(f"tp change p95 {out['tp_change_p95']} steps = {out['tp_change_p95_points']} points > "
                     f"max({th['tp_change_steps']} step, {th['tp_change_points']} points)")
    if out["stab_regret_p99_pct"] > th["stab_regret_p99_pct"]:
        fails.append(f"stabilization regret top 1% {out['stab_regret_p99_pct']}% > {th['stab_regret_p99_pct']}% of the pot")
    for gs in golden:
        if not gs["ok"]:
            fails.append(f"golden {gs['decision']} {gs['base']} seat {gs['seat']}->{gs['to']}BB moved {gs['moved']} "
                         f"< {th['golden_moved']} of the anchor's flip (too flat)")
    out["passed"], out["fails"] = not fails, fails
    return out


# Discrimination policies (the gate must fail the last two and pass the anchor).
def nash_policy_for(spec: dict):
    def policy(sp: R.Spot):
        _, st = anchor(spec, tuple(s / BB for s in sp.stacks))
        return {d: ((st.push[d[1]] if d[0] == "push" else st.call[d[1], d[2]]), None) for d in DECISIONS}
    return policy


def oversensitive_policy_for(spec: dict):
    """The anchor, except a third of the hands flip with the raw stacks' BB digits."""
    nash = nash_policy_for(spec)

    def policy(sp: R.Spot):
        flip = (np.arange(R.N_CLASSES) + sum(sp.stacks) // BB) % 3 == 0
        return {d: (np.where(flip, 1.0 - p, p), None) for d, (p, _) in nash(sp).items()}
    return policy


def flat_policy_for(spec: dict, stacks_bb=(10.0, 10.0, 10.0)):
    """The same actions at every spot (the anchor at 10 BB each)."""
    nash = nash_policy_for(spec)
    return lambda sp: nash(spot(stacks_bb, spec["payouts"]))
