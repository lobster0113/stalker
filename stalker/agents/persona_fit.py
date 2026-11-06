"""Seeded coordinate search for the PRESETS_V2 WTSD levers (#569).

The four levers (`donk_flop`, `probe_turn`, `giveup_weak`, `giveup_turn`) interact across types sitting at the same
table, so hand-tuning stalls (#533). This fits them by coordinate descent on one loss over the whole mixed field:
mean absolute turn fold-to-c-bet error, plus penalties for every guard that `tests/test_persona_v2.py` asserts
(per-seat WTSD +-6pp, flop c-bet/fold +-6pp, river fold error, loose-below-tight fold order).

The game seeds are fixed (same three 6-max tables as the test), so candidates are compared on common random numbers;
the injected `numpy.random.Generator` only orders the coordinates and nothing else, so one seed gives one result.
Not run in tests except on a tiny setting: a real fit is `python scripts/persona_fit.py` (minutes, multi-core).
"""
from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from stalker.agents.persona import PRESETS_V2, PersonaAgent, PersonaParams
from stalker.agents.persona_stats import measure_session

TYPES = list(PRESETS_V2)
TABLES = [TYPES[:6], TYPES[2:8], TYPES[:2] + TYPES[4:8]]  # tests/test_persona_v2.py
LEVERS = ("donk_flop", "probe_turn", "giveup_weak", "giveup_turn")
WTSD_TARGET = dict(zip(TYPES, (0.21, 0.23, 0.27, 0.28, 0.33, 0.40, 0.35, 0.28)))  # note §9
LOOSE, TIGHT = ("calling_station", "maniac", "loose_passive"), ("nit", "weak_tight", "tag", "lag", "pro")
# Penalties start inside the test's limits so a fit at search hands still passes at the test's hands.
WTSD_TOL, FLOP_TOL, RIVER_MAX = 0.05, 0.05, 0.20

Levers = dict[str, tuple[float, float, float, float]]


def current_levers() -> Levers:
    return {n: tuple(getattr(PRESETS_V2[n], k) for k in LEVERS) for n in TYPES}


def with_levers(levers: Mapping[str, Sequence[float]]) -> dict[str, PersonaParams]:
    return {n: dataclasses.replace(PRESETS_V2[n], **dict(zip(LEVERS, levers[n]))) for n in TYPES}


def _table(args: tuple[Mapping[str, Sequence[float]], int, int]) -> list[tuple[str, object]]:
    levers, hands, gi = args
    params, grp = with_levers(levers), TABLES[gi]
    ss = np.random.SeedSequence(gi).spawn(6)
    agents = [PersonaAgent(params[n], np.random.default_rng(s)) for n, s in zip(grp, ss)]
    return list(zip(grp, measure_session(agents, hands, seed=50 + gi)))


def measure(levers: Mapping[str, Sequence[float]], hands: int) -> list[tuple[str, object]]:
    """(type, SeatStats) for every seat of the three test tables, with the test's seeds."""
    return [x for gi in range(len(TABLES)) for x in _table((levers, hands, gi))]


def summarize(seats: list[tuple[str, object]]) -> dict[str, dict[str, float]]:
    """Per-type means over seats (None skipped), as the test computes them."""
    acc: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for n, st in seats:
        for k in ("wtsd", "fold_cbet_turn", "fold_river"):
            if getattr(st, k) is not None:
                acc[n][k].append(getattr(st, k))
    return {n: {k: float(np.mean(v)) for k, v in d.items()} for n, d in acc.items()}


def errors(seats: list[tuple[str, object]]) -> dict[str, float]:
    """Mean absolute turn / river fold errors vs. PRESETS_V2 targets and the worst per-seat WTSD miss."""
    m = summarize(seats)

    def err(n: str, k: str) -> float:  # no opportunity at all (tiny samples) counts as the worst miss
        return abs(m[n][k] - getattr(PRESETS_V2[n], k)) if k in m.get(n, {}) else 1.0

    turn = float(np.mean([err(n, "fold_cbet_turn") for n in TYPES]))
    river = float(np.mean([err(n, "fold_river") for n in TYPES]))
    wtsd = max(abs(st.wtsd - WTSD_TARGET[n]) if st.wtsd is not None else 1.0 for n, st in seats)
    return {"turn": turn, "river": river, "wtsd_worst": wtsd}


def loss(seats: list[tuple[str, object]]) -> float:
    def over(x: float, lim: float) -> float:
        return max(0.0, x - lim)

    e, m = errors(seats), summarize(seats)
    pen = sum(over(abs(st.wtsd - WTSD_TARGET[n]), WTSD_TOL) if st.wtsd is not None else 1.0 for n, st in seats)
    for n, st in seats:
        p = PRESETS_V2[n]
        for got, tgt in ((st.cbet_flop, p.cbet_flop), (st.fold_cbet_flop, p.fold_cbet_flop)):
            pen += over(abs(got - tgt), FLOP_TOL) if got is not None else 1.0
    pen += over(e["river"], RIVER_MAX)
    for k, cap in (("fold_cbet_turn", 0.93), ("fold_river", 0.78)):
        if any(k not in m.get(n, {}) for n in TYPES):
            pen += 1.0
            continue
        pen += over(max(m[n][k] for n in LOOSE) - min(m[n][k] for n in TIGHT), -0.01)
        pen += sum(over(m[n][k], cap) for n in TYPES)
    return e["turn"] + 10.0 * pen


def fit(start: Levers, hands: int, rng: np.random.Generator, step: float = 0.1, min_step: float = 0.025,
        max_passes: int = 6, workers: int = 1, log: Callable[[str], None] | None = None,
        types: Sequence[str] = TYPES) -> tuple[Levers, float]:
    """Coordinate descent: per (type, lever) try +-step, keep the best strict improvement and repeat that step while it
    keeps improving; halve step when a pass stalls.

    Only the levers of `types` move; the loss still covers the whole field.
    """
    pool = ProcessPoolExecutor(workers) if workers > 1 else None

    def evaluate(cands: list[Levers]) -> list[float]:
        jobs = [(c, hands, gi) for c in cands for gi in range(len(TABLES))]
        res = list(pool.map(_table, jobs) if pool else map(_table, jobs))
        k = len(TABLES)
        return [loss([x for r in res[j * k:(j + 1) * k] for x in r]) for j in range(len(cands))]

    coords = [(n, i) for n in types for i in range(len(LEVERS))]
    try:
        cur = {n: tuple(v) for n, v in start.items()}
        best = evaluate([cur])[0]
        for _ in range(max_passes):
            improved = False
            for j in rng.permutation(len(coords)):
                n, i = coords[j]
                cands = []
                for d in (-step, step):
                    v = round(min(1.0, max(0.0, cur[n][i] + d)), 4)
                    if v != cur[n][i]:
                        cands.append({**cur, n: tuple(v if k == i else x for k, x in enumerate(cur[n]))})
                vals = evaluate(cands) if cands else []
                while vals and min(vals) < best - 1e-9:  # pattern move: keep stepping the way that helped
                    prev, (best, cur), improved = cur, (min(vals), cands[int(np.argmin(vals))]), True
                    if log:
                        log(f"{n} {LEVERS[i]}={cur[n][i]} loss={best:.4f}")
                    v = round(min(1.0, max(0.0, 2 * cur[n][i] - prev[n][i])), 4)
                    cands = [] if v == cur[n][i] else [{**cur, n: tuple(v if k == i else x for k, x in enumerate(cur[n]))}]
                    vals = evaluate(cands) if cands else []
            if not improved:
                if step / 2 < min_step:
                    break
                step /= 2
    finally:
        if pool:
            pool.shutdown()
    return cur, best
