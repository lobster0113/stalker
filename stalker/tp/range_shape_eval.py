"""Discrimination of the `opp.range` shape answer on river spots (#159, ADR 0011 adoption check).

Question: when the true opponent range is polar or condensed, does picking the right shape score
clearly better than reading it as linear, by more than the score lost to the input itself?

Spots are river subgames built from seeded parts (no hidden cards are used for grading inputs):
- board: 5 random cards; my range: top `MY_TOP` of preflop hands; opponent preflop range: top W%.
- the opponent's river range is the preflop range filtered by an action archetype on combo strength
  (equity vs my range, the same strength `range_shape.strength_bins` uses):
    polar     bet = value (strongest v share) + bluffs (weakest b share)
    condensed check-call = the middle band
    linear    bet/raise for value = the strongest q share
  Edges are soft (logistic in the strength percentile) so ranges are not razor cut.

Answers compared on each spot (all graded by `range_shape.score`, EMD on the 5 bins):
- shape:        the template of the true shape (one tap; mid tier)
- linear:       the linear template (the "read it as linear" mistake, same tier)
- best_width:   the best-scoring beginner width answer over a 1% grid (most charitable linear read)
- quantized:    the true bins rounded to the input step (largest remainder) = loss from the input alone
- noisy:        the true bins with N(0, sigma) per bar, clipped and renormalised = a pessimistic input

Strength is computed once per combo from a 7-card rank table, which equals the exact equity of
`stalker.tp.reference.equity` against my range on the river (checked in tests).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from stalker.core.cards import COMBOS, N_CARDS
from stalker.core.evaluator import evaluate
from stalker.core.ranges import combo_top_pct
from stalker.tp import range_shape as RS

MY_TOP = 0.30
OPP_TOPS = (0.15, 0.25, 0.40)
ARCHETYPES = ("polar", "condensed", "linear")
SOFT = 0.04          # logistic edge width in strength-percentile units
WIDTH_GRID = np.linspace(0.01, 1.0, 100)
INPUT_STEP = 0.05    # bars move in 5pp chips
NOISE_SIGMA = 0.05


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x / SOFT))


def _conflict() -> np.ndarray:
    m = np.zeros((len(COMBOS), N_CARDS), bool)
    for i, (a, b) in enumerate(COMBOS):
        m[i, a] = m[i, b] = True
    return m


_CARD_MASK = _conflict()
_COMPAT = ~(_CARD_MASK.astype(np.int8) @ _CARD_MASK.T.astype(np.int8)).astype(bool)


def combo_strength(opp_w: np.ndarray, my_w: np.ndarray, board) -> np.ndarray:
    """Equity of every combo against my range on a river board (nan where blocked or no partner)."""
    board = tuple(board)
    if len(board) != 5:
        raise ValueError("combo_strength is the river shortcut; use range_shape.strength_bins on the turn")
    on_board = _CARD_MASK[:, list(board)].any(axis=1)
    ranks = np.array([evaluate([a, b, *board]) if not on_board[i] else -1 for i, (a, b) in enumerate(COMBOS)])
    mine = np.where(on_board, 0.0, my_w)
    out = np.full(len(COMBOS), np.nan)
    for i in np.flatnonzero((opp_w > 0) & ~on_board):
        w = mine * _COMPAT[i]
        tot = w.sum()
        if tot > 0:
            r = ranks[i]
            out[i] = (w[ranks < r].sum() + 0.5 * w[ranks == r].sum()) / tot
    return out


def bins_from_strength(weights: np.ndarray, strength: np.ndarray) -> np.ndarray:
    ok = (weights > 0) & ~np.isnan(strength)
    idx = np.searchsorted(RS.EDGES, strength[ok], side="right")
    mass = np.bincount(idx, weights=weights[ok], minlength=5)
    if mass.sum() == 0:
        raise ValueError("opponent range is empty on this board")
    return mass / mass.sum()


def _percentile(weights, strength):
    """Weighted strength percentile of each combo inside the range (0 weakest .. 1 strongest)."""
    ok = (weights > 0) & ~np.isnan(strength)
    order = np.flatnonzero(ok)[np.argsort(strength[ok], kind="stable")]
    cum = np.cumsum(weights[order])
    pct = np.full(len(weights), np.nan)
    pct[order] = (cum - weights[order] / 2) / cum[-1]
    return pct


def archetype_range(kind: str, pre_w, strength, rng: np.random.Generator) -> np.ndarray:
    p = np.nan_to_num(_percentile(pre_w, strength), nan=-1.0)
    live = (p >= 0).astype(float)
    if kind == "polar":
        v = rng.uniform(0.15, 0.35)
        b = v * rng.uniform(0.4, 0.8)        # bluff:value about pot-sized to half-pot odds
        f = _sig(p - (1 - v)) + _sig(b - p)
    elif kind == "condensed":
        lo, hi = rng.uniform(0.25, 0.45), rng.uniform(0.70, 0.85)
        f = _sig(p - lo) * _sig(hi - p)
    elif kind == "linear":
        q = rng.uniform(0.30, 0.60)
        f = _sig(p - (1 - q))
    else:
        raise ValueError(f"unknown archetype {kind!r}; use one of {ARCHETYPES}")
    return pre_w * f * live


def quantize(b, step: float = INPUT_STEP) -> np.ndarray:
    """Round a distribution to `step` chips that still sum to 1 (largest remainder)."""
    n = int(round(1 / step))
    raw = np.asarray(b, float) * n
    q = np.floor(raw)
    q[np.argsort(-(raw - q))[: n - int(q.sum())]] += 1
    return q / n


def noisy(b, rng: np.random.Generator, sigma: float = NOISE_SIGMA) -> np.ndarray:
    x = np.clip(np.asarray(b, float) + rng.normal(0, sigma, 5), 0, None)
    return x / x.sum() if x.sum() > 0 else np.full(5, 0.2)


@dataclass
class Spot:
    archetype: str
    opp_top: float
    truth: np.ndarray
    shape: str
    scores: dict


def make_spot(rng: np.random.Generator, archetype: str) -> Spot:
    pct = combo_top_pct()
    while True:
        board = tuple(int(c) for c in rng.choice(N_CARDS, 5, replace=False))
        my_w = (pct <= MY_TOP).astype(float)
        opp_top = float(rng.choice(OPP_TOPS))
        pre_w = (pct <= opp_top).astype(float)
        strength = combo_strength(pre_w, my_w, board)
        w = archetype_range(archetype, pre_w, strength, rng)
        if w.sum() >= 5:                     # at least a handful of combos survive
            break
    truth = bins_from_strength(w, strength)
    best_width = max(RS.score(RS.width_default(float(x)), truth) for x in WIDTH_GRID)
    scores = {
        "shape": RS.score(RS.TEMPLATES[RS.shape_of(truth)], truth),
        "linear": RS.score(RS.TEMPLATES["linear"], truth),
        "best_width": best_width,
        "quantized": RS.score(quantize(truth), truth),
        "noisy": RS.score(noisy(truth, rng), truth),
    }
    return Spot(archetype, opp_top, truth, RS.shape_of(truth), scores)


def run(n_per_archetype: int, seed: int) -> list[Spot]:
    rng = np.random.default_rng(seed)
    return [make_spot(rng, a) for a in ARCHETYPES for _ in range(n_per_archetype)]


def summarize(spots: list[Spot]) -> dict:
    """Per true shape: mean scores, the shape-vs-linear gap and the input loss to compare it with."""
    out = {}
    for shape in RS.SHAPES:
        s = [x for x in spots if x.shape == shape]
        if not s:
            continue
        col = {k: np.array([x.scores[k] for x in s], float) for k in s[0].scores}
        gap_t = col["shape"] - col["linear"]
        gap_w = col["shape"] - col["best_width"]
        out[shape] = {
            "n": len(s),
            "mean": {k: float(v.mean()) for k, v in col.items()},
            "gap_vs_linear_template": float(gap_t.mean()),
            "gap_vs_best_width": float(gap_w.mean()),
            "gap_vs_best_width_p10": float(np.percentile(gap_w, 10)),
            "share_gap_vs_best_width_positive": float((gap_w > 0).mean()),
            # per spot: does the shape answer beat the best linear read by more than a noisy entry loses?
            "share_gap_gt_noisy_loss": float((gap_w > 100 - col["noisy"]).mean()),
            "input_loss_quantized": float(100 - col["quantized"].mean()),
            "input_loss_noisy": float(100 - col["noisy"].mean()),
        }
    return out


def main(argv=None) -> None:
    import argparse
    import json

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=200, help="spots per archetype")
    ap.add_argument("--seed", type=int, default=159)
    a = ap.parse_args(argv)
    spots = run(a.n, a.seed)
    cross = {a_: {sh: sum(1 for x in spots if x.archetype == a_ and x.shape == sh) for sh in RS.SHAPES}
             for a_ in ARCHETYPES}
    print(json.dumps({"n_per_archetype": a.n, "seed": a.seed, "archetype_to_shape": cross,
                      "by_true_shape": summarize(spots)}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
