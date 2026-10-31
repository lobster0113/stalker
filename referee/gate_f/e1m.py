"""Gate F v0 on E1m (#313): follow robustness on 3-handed ICM push/fold, error model 1 (synthetic).

The E1 gate (`referee.gate_f`) carried to `referee.anchors.icm_reference`. A policy is
`policy(spot) -> {decision: FollowSpec}` for the five E1m decisions (`referee.gate_s.e1m.DECISIONS`);
the follower perceives each TP value with the tier's Gaussian error and plays the perceived bin's
action, all seats at once. Expected losses are exact (bin probabilities, no sampling), in % of the
prize pool, per spot:
- exploitability: the follower profile's summed per-seat best-response gain;
- anchor_loss: per seat, what the follower gives up against the anchor's other seats versus the
  best response to them (unconstrained fictitious play, the spot set's `anchor_iters`), summed;
- each also for the noiseless policy, and the difference (follower - noiseless).
Report-only like E1: E1m has no persona field (`VERDICT`).
"""
from __future__ import annotations

import numpy as np

from referee.anchors import icm_reference as R
from referee.gate_f import SIGMA, VERDICT, follow
from referee.gate_s import e1m as S


def _profile(base: R.Strategy, probs: dict, seats=None) -> R.Strategy:
    st = base.copy()
    for d, p in probs.items():
        owner = d[1]
        if seats is not None and owner not in seats:
            continue
        if d[0] == "push":
            st.push[d[1]] = p
        else:
            st.call[d[1], d[2]] = p
    return st


def losses(spec: dict, stacks, probs: dict) -> tuple[float, float]:
    """(exploitability, anchor_loss) of a full profile, % of the prize pool."""
    sp, tree, nash, _ = S._solve(tuple(float(x) for x in stacks), tuple(spec["payouts"]), spec["anchor_iters"])
    pool = sp.prize_pool
    st = _profile(nash, probs)
    expl = float(tree.evaluate(st).gains(st, sp.n).sum())
    anchor_loss = 0.0
    for seat in range(sp.n):
        mine = _profile(nash, probs, {seat})
        anchor_loss += float(tree.evaluate(mine).gains(mine, sp.n)[seat])
    return 100.0 * expl / pool, 100.0 * anchor_loss / pool


def evaluate(policy, stacks_list, tier: str, sigma: float | None = None, spec: dict | None = None) -> dict:
    spec = spec or S.load()[0]
    sigma = SIGMA[tier] if sigma is None else sigma
    rows = []
    for stacks in stacks_list:
        fs = policy(S.spot(stacks, spec["payouts"]))
        ex0, al0 = losses(spec, stacks, {d: f.probs() for d, f in fs.items()})
        ex1, al1 = losses(spec, stacks, {d: follow(f, sigma) for d, f in fs.items()})
        rows.append({"stacks": list(stacks), "anchor_loss_pct": round(al1, 5), "anchor_loss_noiseless_pct": round(al0, 5),
                     "anchor_loss_added_pct": round(al1 - al0, 5), "exploitability_pct": round(ex1, 5),
                     "exploitability_noiseless_pct": round(ex0, 5), "exploitability_added_pct": round(ex1 - ex0, 5)})
    mean = {k: round(float(np.mean([r[k] for r in rows])), 5) for k in rows[0] if k != "stacks"}
    return {"env": "e1m", "tier": tier, "sigma": sigma, "spots": len(rows), "mean": mean, "rows": rows, "verdict": VERDICT}
