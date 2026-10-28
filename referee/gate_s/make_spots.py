"""Regenerate spots_v1.json: python -m referee.gate_s.make_spots (changing the set changes its sha256).

Base spots: every E1 grid stack (1-15 BB, 0.5 steps) for both seats and both BB antes. Golden spots:
for each seat, ante and bucket, the in-bucket stack pair whose clear-flip mass under the anchor is
largest, kept when that mass is at least MIN_FLIP_MASS of the hands.
"""
import json
from pathlib import Path

from referee import gate_s as S

EDGES = [5.0, 10.0, 15.0]   # docs/TP.md §6 effective-stack buckets inside E1
MIN_FLIP_MASS = 0.03

spec = {"version": 1, "seed": 280, "per_base": 6, "bucket_edges": EDGES, "flip_margin_pot": 0.01,
        "thresholds": {"tv_p95": 0.15, "tp_change_steps": 1, "stab_regret_p99_pct": 2.0, "golden_moved": 0.5},
        "base": [[seat, s, ante] for seat in S.SEATS for ante in (0.0, 1.0) for s in S.grid(EDGES)]}
golden = []
g = S.grid(EDGES)
for seat in S.SEATS:
    for ante in (0.0, 1.0):
        for k in range(len(EDGES)):
            stacks = [s for s in g if S._bucket(s, EDGES) == k]
            best = None
            for i, a in enumerate(stacks):
                for b in stacks[i + 1:]:
                    _, exc, _ = S.roles(seat, ante, a, b, spec["flip_margin_pot"])
                    m = float(S._anchor(seat, a, ante)[2][exc].sum())
                    if best is None or m > best[0]:
                        best = (m, a, b)
            if best and best[0] >= MIN_FLIP_MASS:
                golden.append({"seat": seat, "ante": ante, "a": best[1], "b": best[2], "flip_mass": round(best[0], 4)})
spec["golden"] = golden
# LF on every OS: the loader hashes the raw bytes.
(Path(__file__).resolve().parent / "spots_v1.json").write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8", newline="\n")
print(len(spec["base"]), "base spots,", len(golden), "golden")
