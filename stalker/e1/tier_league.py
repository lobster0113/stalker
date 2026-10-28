"""E1 tier league (#290): TP bottleneck policies of several tiers trained against a mixed field.

`tp_pushfold.train` is same-tier self-play: a beginner SB learns against a beginner BB. Its coarse
equilibrium can move against the anchor (PR #289: the beginner SB's middle bin shoves 0.35 -> 0.48
from 10.5 to 15BB while Nash goes 0.83 -> 0.29; with a pro BB it goes 0.94 -> 0.17). Users do not
face same-tier bots, so here every tier's policy best-responds (in its own bucket space) to a field,
a weighted mix of all tiers' running averages, and all tiers learn together (population fictitious
play). Payoffs are linear in the opponent's per-class probabilities, so the best response to the
mix is the best response to the mix's mean policy.

`mix={"beginner": 1}` with tiers=("beginner",) is the same-tier self-play of `tp_pushfold.train`.
The TP value each tier reads is measured against the field (the assumed opponent): SB equity when
called by the field's calling range, BB equity against the field's shoving range, on the tier's
quantile (rank) scale.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from referee.anchors import pushfold as P
from stalker.e1 import tp_pushfold as T

TIERS = ("beginner", "mid", "pro")
MIXES = {"self": None, "pro": {"pro": 1.0}, "even": {"beginner": 1 / 3, "mid": 1 / 3, "pro": 1 / 3}}


@dataclass
class League:
    stack: float
    ante: float
    scale: str
    mix: dict[str, float]
    push: dict[str, np.ndarray]     # per tier, per class SB shove probability (a function of its bucket)
    call: dict[str, np.ndarray]     # per tier, per class BB call probability
    sb_bins: dict[str, np.ndarray]  # per tier, the SB bucket each class reads against the field
    bb_bins: dict[str, np.ndarray]
    call_field: np.ndarray | None = None  # the field's calls the SB bins were read against
    push_field: np.ndarray | None = None  # the field's shoves the BB bins were read against
    consistent: bool = True         # the SB bins equal those read against the delivered field


def _mean(pol: dict[str, np.ndarray], mix: dict[str, float]) -> np.ndarray:
    return sum(w * pol[t] for t, w in mix.items())


def train(stack: float, ante: float, tiers=TIERS, mix: dict[str, float] | None = None, iters: int = 1500,
          scale: str = "quantile") -> League:
    """mix None = each tier against itself (same-tier self-play, one independent run per tier)."""
    if mix is None and len(tiers) == 1:
        mix = {tiers[0]: 1.0}
    if mix is None:
        runs = {t: train(stack, ante, (t,), {t: 1.0}, iters, scale) for t in tiers}
        return League(stack, ante, scale, {}, {t: r.push[t] for t, r in runs.items()}, {t: r.call[t] for t, r in runs.items()},
                      {t: r.sb_bins[t] for t, r in runs.items()}, {t: r.bb_bins[t] for t, r in runs.items()},
                      None, None, all(r.consistent for r in runs.values()))
    if not set(mix) <= set(tiers) or abs(sum(mix.values()) - 1) > 1e-9:
        raise ValueError(f"mix {mix} must be weights over trained tiers {tiers} summing to 1")
    p, sb_call, bb_gain = P._payoffs(stack, ante)
    w_sb, w_bb = p.sum(axis=1), p.sum(axis=0)
    q_sb = {t: T._bucketer(t, scale, w_sb) for t in tiers}
    q_bb = {t: T._bucketer(t, scale, w_bb) for t in tiers}
    push = {t: np.full(169, 0.5) for t in tiers}
    call = {t: np.full(169, 0.5) for t in tiers}

    # Same order as tp_pushfold.train: SB buckets against the field's average calls, BB buckets
    # against the field's projected shoves, so mix={t: 1} reproduces it exactly.
    def sb_bins(call):
        c_f = _mean(call, mix)
        return {t: q_sb[t](T.sb_equity_when_called(c_f)) for t in tiers}, c_f

    def bb_bins(s):
        s_f = _mean(s, mix)
        return {t: q_bb[t](T.bb_equity(s_f)) for t in tiers}, s_f

    for k in range(1, iters + 1):
        sb_b, _ = sb_bins(call)
        s = {t: T._project(push[t], sb_b[t], w_sb) for t in tiers}
        bb_b, _ = bb_bins(s)
        c = {t: T._project(call[t], bb_b[t], w_bb) for t in tiers}
        pu, fo = P._sb_values(_mean(c, mix), p, sb_call, ante)
        g = P._bb_gain(_mean(s, mix), p, bb_gain)
        for t in tiers:
            nb, nc = sb_b[t].max() + 1, bb_b[t].max() + 1
            s_br = (np.bincount(sb_b[t], pu, nb) > np.bincount(sb_b[t], fo, nb)).astype(float)[sb_b[t]]
            c_br = (np.bincount(bb_b[t], g, nc) > 0).astype(float)[bb_b[t]]
            push[t] += (s_br - push[t]) / (k + 1)
            call[t] += (c_br - call[t]) / (k + 1)
    # Deliver functions of the TP value each tier reads against the delivered field (as train does).
    avg_push, avg_call = push, call
    for _ in range(50):
        sb_b, call_field = sb_bins(call)
        push = {t: T._project(avg_push[t], sb_b[t], w_sb) for t in tiers}
        bb_b, push_field = bb_bins(push)
        new_call = {t: T._project(avg_call[t], bb_b[t], (p * push[t][:, None]).sum(axis=0)) for t in tiers}
        if all(np.array_equal(new_call[t], call[t]) for t in tiers):
            break
        call = new_call
    # If the bucketings cycle (no fixed point in 50 passes) the SB's bins are those of the last pass,
    # one step stale against the delivered calls; `consistent` says whether that happened.
    consistent = all(np.array_equal(a, b) for a, b in zip(sb_bins(call)[0].values(), sb_b.values()))
    return League(stack, ante, scale, dict(mix), push, call, sb_b, bb_b, call_field, push_field, consistent)


def gate_s_policy(tier: str, mix_name: str, iters: int = 1500, scale: str = "quantile"):
    """`referee.gate_s` policy: the tier's league policy at each spot, with its TP bins."""
    def policy(seat: str, stack: float, ante: float):
        r = _league(stack, ante, _tiers(tier, mix_name), mix_name, iters, scale)
        return (r.push[tier], r.sb_bins[tier]) if seat == "sb" else (r.call[tier], r.bb_bins[tier])
    return policy


def gate_f_policy(tier: str, mix_name: str, iters: int = 1500, scale: str = "quantile"):
    """`referee.gate_f` policy: the tier's league policy as a FollowSpec (TP value vs the field)."""
    from referee.gate_f import FollowSpec

    def policy(seat: str, stack: float, ante: float) -> FollowSpec:
        r = _league(stack, ante, _tiers(tier, mix_name), mix_name, iters, scale)
        p, _, _ = P._payoffs(stack, ante)
        if seat == "sb":
            eq, probs, w = T.sb_equity_when_called(r.call_field), r.push[tier], p.sum(axis=1)
        else:
            eq, probs, w = T.bb_equity(r.push_field), r.call[tier], p.sum(axis=0)
        values, edges = T.tp_values(tier, scale, eq, w)
        b = np.searchsorted(edges, values, side="right")
        occupied = np.unique(b)
        nearest = occupied[np.abs(np.arange(len(edges) + 1)[:, None] - occupied[None, :]).argmin(axis=1)]
        bin_probs = np.zeros(len(edges) + 1)
        bin_probs[b] = probs
        return FollowSpec(bin_probs[nearest], values, edges)
    return policy


@lru_cache(maxsize=512)
def _league(stack: float, ante: float, tiers: tuple[str, ...], mix_name: str, iters: int, scale: str) -> League:
    # One league run serves every tier's adapter at a spot (all tiers are trained together).
    return train(stack, ante, tiers, MIXES[mix_name], iters, scale)


def _tiers(tier: str, mix_name: str) -> tuple[str, ...]:
    return (tier,) if MIXES[mix_name] is None else TIERS


def table(tiers=("beginner", "mid"), mixes=("self", "pro", "even"), iters: int = 1500, stacks=None, antes=None) -> list[dict]:
    """Per (tier, training field): exact Q4 exploitability and loss vs the Nash anchor's opponent (mean
    over E1 spots), Gate S summary on spots v1, Gate F follower loss (the tier's sigma)."""
    from referee import gate_f, gate_s

    spots = [(s, a) for a in (antes or T.E1_ANTES) for s in (stacks or T.E1_STACKS)]
    spec, _ = gate_s.load()
    rows = []
    for mix_name in mixes:
        for tier in tiers:
            ex, nl = [], []
            for stack, ante in spots:
                r = _league(stack, ante, _tiers(tier, mix_name), mix_name, iters, "quantile")
                ex.append(P.exploitability(stack, ante, r.push[tier], r.call[tier]))
                nl.append(sum(gate_f.nash_loss(stack, ante, r.push[tier], r.call[tier])))
            s = gate_s.evaluate(gate_s_policy(tier, mix_name, iters), spec)
            f = gate_f.evaluate(gate_f_policy(tier, mix_name, iters), spots, tier)["mean"]
            rows.append({"tier": tier, "field": mix_name, "spots": len(spots), "exploitability": round(float(np.mean(ex)), 5),
                         "nash_loss": round(float(np.mean(nl)), 5), "gate_s_passed": s["passed"], "gate_s_tv_p95": s["tv_p95"],
                         "gate_s_regret_p99_pct": s["stab_regret_p99_pct"], "gate_s_tp_change_p95": s["tp_change_p95"],
                         "gate_s_golden": f"{sum(g['ok'] for g in s['golden'])}/{len(s['golden'])}",
                         "gate_f_nash_loss": f["nash_loss"], "gate_f_added": f["nash_loss_added"]})
    return rows


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="E1 tier league comparison table (local reference numbers)")
    ap.add_argument("--iters", type=int, default=1500)
    ap.add_argument("--tiers", nargs="*", default=["beginner", "mid"], choices=list(TIERS))
    ap.add_argument("--mixes", nargs="*", default=list(MIXES), choices=list(MIXES))
    a = ap.parse_args()
    for row in table(a.tiers, a.mixes, a.iters):
        print(json.dumps(row), flush=True)
