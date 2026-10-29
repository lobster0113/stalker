"""Regenerate spots_e1m_v1.json: python -m referee.gate_s.make_spots_e1m (changing the set changes its sha256).

Base spots: the E1m research spots plus mixed-stack triples (BTN, SB, BB in BB). Golden spots: for each
decision and each bucket of the moved seat, the in-bucket move of one seat whose clear-flip mass under
the anchor is largest over all bases, kept when that mass is at least MIN_FLIP_MASS of the decision's weight.
"""
import json
from pathlib import Path

from referee.gate_s import e1m as S

EDGES = [5.0, 10.0, 15.0, 25.0]   # docs/TP.md §6 effective-stack buckets up to 25 BB
MIN_FLIP_MASS = 0.03

spec = {"version": 1, "seed": 313, "per_base": 6, "payouts": [0.5, 0.3, 0.2], "anchor_iters": 400,
        "bucket_edges": EDGES, "grid": [float(s) for s in range(2, 26)], "flip_margin_pot": 0.01,
        "thresholds": {"tv_p95": 0.15, "tp_change_steps": 1, "tp_change_points": 10, "stab_regret_p99_pct": 2.0, "golden_moved": 0.5},
        "base": [[10, 10, 10], [15, 15, 15], [20, 20, 20], [5, 15, 15], [25, 10, 8], [15, 15, 5],
                 [8, 12, 20], [12, 4, 9]],
        "golden": []}
best = {}
for base in (tuple(float(x) for x in b) for b in spec["base"]):
    for seat, s in S.moves(spec, base):
        b = base[:seat] + (s,) + base[seat + 1:]
        for d in S.DECISIONS:
            if not S.reached(spec, base, b, d):
                continue
            _, exc, _ = S.roles(spec, base, b, d)
            m = float(S._dec(spec, base, d)[1][exc].sum())
            key = (d, S.bucket(base[seat], EDGES))
            if m >= MIN_FLIP_MASS and (key not in best or m > best[key][0]):
                best[key] = (m, base, seat, s)
spec["golden"] = [{"decision": list(d), "base": list(base), "seat": seat, "to": s, "flip_mass": round(m, 4)}
                  for (d, _), (m, base, seat, s) in sorted(best.items())]
# LF on every OS: the loader hashes the raw bytes.
(Path(__file__).resolve().parent / "spots_e1m_v1.json").write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8", newline="\n")
print(len(spec["base"]), "base spots,", len(spec["golden"]), "golden")
