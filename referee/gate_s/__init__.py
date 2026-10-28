"""Gate S v0 (#280): insensitivity on E1 heads-up push/fold, judged against the exact Nash anchor.

A policy is `policy(seat, stack_bb, ante_bb) -> (probs, tp_bins)` over the 169 hand classes:
`probs` is the shove (SB) or call (BB) probability, `tp_bins` the TP value each hand reads on the
policy's own scale (bin index, so one bin = one scale step) or None for a policy without TP values.
A policy may carry `tp_step_points` (0-100 points per scale step); without it a step counts as the
whole scale, so the tolerance falls back to one step.

A perturbation moves the stack inside its `docs/TP.md` §6 bucket (E1: <=5, 5-10, 10-15 BB) on the
anchor's 0.5 BB grid; seat and ante stay. For each (base, perturbed) pair, per hand, the anchor's
EV advantage of the aggressive action over folding against the Nash opponent decides the hand's role:
- stable: the anchor's best action is the same at both stacks. The policy should not move here
  (TV metric).
- sensitivity exception (§6 ④): the anchor's best action flips and both margins are at least
  `flip_margin_pot` of the pot. The policy may move here, and on the golden spots it must move in the
  anchor's direction (flattening fails).
- other flips (a margin below the threshold) count for neither.
Measured per pair (aggregate over hands, mass-weighted):
- tv: mean |p - p'| over stable hands;
- tp_change: weighted 95th percentile of |bin - bin'| over all hands (scale steps);
- stab_regret: max(0, L' - L), where L is the policy's loss against the anchor's best at the spot,
  per decision reached, in % of the pot at the decision (SB 1.5 + ante, BB facing a shove stack + 1 + ante).
Pass (ADR 0016): tv p95 <= 0.15, tp_change p95 <= max(1 step, `tp_change_points` points), stab_regret top 1% <= 2% of
the pot, and every golden spot moved at least half of its flip mass in the anchor's direction.
Boundary cliffs (adjacent grid stacks across a bucket edge, tv > 0.15) are reported, not gated.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from referee.anchors import pushfold as P

SPOTS_V1 = Path(__file__).resolve().parent / "spots_v1.json"
SEATS = ("sb", "bb")


class SpotError(ValueError):
    pass


def load(path: Path = SPOTS_V1) -> tuple[dict, str]:
    raw = path.read_bytes()
    spec = json.loads(raw)
    for key in ("version", "seed", "per_base", "bucket_edges", "flip_margin_pot", "thresholds", "base", "golden"):
        if key not in spec:
            raise SpotError(f"{path.name}: missing {key!r}; regenerate with python -m referee.gate_s.make_spots")
    if len(spec["golden"]) < 5:
        raise SpotError(f"{path.name}: {len(spec['golden'])} golden spots; Gate S needs at least 5")
    for g in spec["golden"]:
        if _bucket(g["a"], spec["bucket_edges"]) != _bucket(g["b"], spec["bucket_edges"]):
            raise SpotError(f"{path.name}: golden {g} crosses a bucket edge; golden spots are in-bucket")
    return spec, hashlib.sha256(raw).hexdigest()


def _bucket(stack: float, edges) -> int:
    return next((i for i, e in enumerate(edges) if stack <= e), len(edges))


def grid(edges) -> list[float]:
    return [s for s in P.STACKS if s <= edges[-1]]


def pairs(spec: dict) -> list[tuple[str, float, float, float]]:
    """(seat, ante, base stack, perturbed stack): `per_base` in-bucket draws per base spot, seeded."""
    rng = np.random.default_rng(spec["seed"])
    g, edges = grid(spec["bucket_edges"]), spec["bucket_edges"]
    out = []
    for seat, stack, ante in (tuple(b) for b in spec["base"]):
        same = [s for s in g if s != stack and _bucket(s, edges) == _bucket(stack, edges)]
        for s2 in rng.choice(same, size=min(spec["per_base"], len(same)), replace=False):
            out.append((seat, float(ante), float(stack), float(s2)))
    return out


@lru_cache(maxsize=None)
def _anchor(seat: str, stack: float, ante: float):
    """Per hand: (advantage of the aggressive action in bb per decision, EV pieces for losses, mass, pot)."""
    push, call = P.strategy(stack, ante)
    p, sb_call, bb_gain = P._payoffs(stack, ante)
    if seat == "sb":
        pu, fo = P._sb_values(call, p, sb_call, ante)
        mass = p.sum(axis=1)
        return (pu - fo) / mass, (pu, fo), mass, 1.5 + ante, 1.0
    g = P._bb_gain(push, p, bb_gain)
    reach_b = (p * push[:, None]).sum(axis=0)
    adv = np.where(reach_b > 0, g / np.where(reach_b > 0, reach_b, 1.0), 0.0)
    return adv, (g, np.zeros_like(g)), p.sum(axis=0), stack + 1.0 + ante, float(reach_b.sum())


def loss_pct(seat: str, stack: float, ante: float, probs: np.ndarray) -> float:
    """The policy's loss against the anchor's best action at this spot, per decision, % of the pot."""
    _, (agg, fold), _, pot, reach = _anchor(seat, stack, ante)
    loss = float((np.maximum(agg, fold) - (probs * agg + (1 - probs) * fold)).sum()) / reach
    return 100.0 * loss / pot


def roles(seat: str, ante: float, a: float, b: float, margin: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(stable mask, exception mask, direction +1/-1 of the anchor's move on exception hands)."""
    adv_a, _, mass, pot_a, _ = _anchor(seat, a, ante)
    adv_b, _, _, pot_b, _ = _anchor(seat, b, ante)
    best_a, best_b = adv_a > 0, adv_b > 0
    stable = best_a == best_b
    clear = (np.abs(adv_a) >= margin * pot_a) & (np.abs(adv_b) >= margin * pot_b)
    return stable, ~stable & clear, np.where(best_b, 1.0, -1.0)


def _wpct(x: np.ndarray, w: np.ndarray, q: float) -> float:
    order = np.argsort(x)
    cum = np.cumsum(w[order]) / w.sum()
    return float(x[order][min(np.searchsorted(cum, q / 100.0), len(x) - 1)])


def evaluate(policy, spec: dict | None = None) -> dict:
    spec = spec or load()[0]
    th, margin, edges = spec["thresholds"], spec["flip_margin_pot"], spec["bucket_edges"]
    cache = {}

    def act(seat, stack, ante):
        k = (seat, stack, ante)
        if k not in cache:
            probs, bins = policy(seat, stack, ante)
            probs = np.asarray(probs, dtype=float)
            if probs.shape != (169,) or ((probs < 0) | (probs > 1)).any():
                raise ValueError("policy must return 169 probabilities in [0, 1] (HAND_CLASSES order)")
            cache[k] = (probs, None if bins is None else np.asarray(bins))
        return cache[k]

    step_pts = float(getattr(policy, "tp_step_points", 100.0))
    tv, tp, reg, tv_seat = [], [], [], []
    for seat, ante, a, b in pairs(spec):
        (pa, ba), (pb, bb) = act(seat, a, ante), act(seat, b, ante)
        stable, _, _ = roles(seat, ante, a, b, margin)
        mass = _anchor(seat, a, ante)[2]
        w = mass * stable
        tv.append(float((w * np.abs(pa - pb)).sum() / w.sum()) if w.sum() > 0 else 0.0)
        tv_seat.append(seat)
        if ba is not None:
            tp.append(_wpct(np.abs(ba - bb).astype(float), mass, 95))
        reg.append(max(0.0, loss_pct(seat, b, ante, pb) - loss_pct(seat, a, ante, pa)))
    golden = []
    for gs in spec["golden"]:
        seat, ante, a, b = gs["seat"], float(gs["ante"]), float(gs["a"]), float(gs["b"])
        _, exc, direction = roles(seat, ante, a, b, margin)
        w = _anchor(seat, a, ante)[2] * exc
        moved = float((w * np.maximum(0.0, direction * (act(seat, b, ante)[0] - act(seat, a, ante)[0]))).sum() / w.sum())
        golden.append({**gs, "moved": round(moved, 4), "ok": moved >= th["golden_moved"]})
    cliffs = []
    g = grid(edges)
    for seat in SEATS:
        for ante in sorted({float(x[2]) for x in spec["base"]}):
            for lo, hi in zip(g, g[1:]):
                if _bucket(lo, edges) != _bucket(hi, edges):
                    stable, _, _ = roles(seat, ante, lo, hi, margin)
                    w = _anchor(seat, lo, ante)[2] * stable
                    cliffs.append(float((w * np.abs(act(seat, lo, ante)[0] - act(seat, hi, ante)[0])).sum() / w.sum()) > th["tv_p95"])
    out = {"pairs": len(tv), "tv_p95": round(float(np.percentile(tv, 95)), 4),
           "tv_p95_by_seat": {s: round(float(np.percentile([t for t, x in zip(tv, tv_seat) if x == s], 95)), 4)
                              for s in SEATS if s in tv_seat},
           "tp_change_p95": None if not tp else round(float(np.percentile(tp, 95)), 3),
           "tp_change_p95_points": None if not tp else round(float(np.percentile(tp, 95)) * step_pts, 3),
           "stab_regret_mean_pct": round(float(np.mean(reg)), 4), "stab_regret_p99_pct": round(float(np.percentile(reg, 99)), 4),
           "cliff_ratio": round(sum(cliffs) / len(cliffs), 3) if cliffs else 0.0,
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
            fails.append(f"golden {gs['seat']} ante {gs['ante']} {gs['a']}->{gs['b']}BB moved {gs['moved']} < {th['golden_moved']} "
                         "of the anchor's flip (too flat)")
    out["passed"], out["fails"] = not fails, fails
    return out


# Discrimination policies (the gate must fail the first two and pass the anchor).
def nash_policy(seat, stack, ante):
    push, call = P.strategy(stack, ante)
    return (push if seat == "sb" else call), None


def oversensitive_policy(seat, stack, ante):
    """The anchor, except a third of the hands flip with the raw stack's half-BB digit."""
    probs, _ = nash_policy(seat, stack, ante)
    flip = (np.arange(169) + int(round(stack * 2))) % 3 == 0
    return np.where(flip, 1.0 - probs, probs), None


def flat_policy(seat, stack, ante):
    """The same actions at every stack (the anchor at 10 BB)."""
    return nash_policy(seat, 10.0, ante)
