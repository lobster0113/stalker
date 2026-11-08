"""Gate E spike (#600): fixed 1·3·7-day review vs a Leitner-style adaptive scheduler.

Both schedulers expose `next_due(item_state, grade) -> (new_state, days_until_due | None)` and run in the
same harness against the same simulated learner (same per-seed item difficulties, same recall draws).
`None` means "no further review". Grade is 1 (recalled) or 0 (forgot).

The learner has per-item memory strength S (days). Two forgetting models, so the result does not depend
on the one assumption a scheduler happens to share:
- "exp":   recall p = exp(-t / S);        success multiplies S by `gain`, failure multiplies by `lapse`.
- "power": recall p = (1 + t / S) ** -0.7; success adds `gain_add` * S (spacing effect: bigger gap
           since last review => bigger gain), failure multiplies by `lapse`.
The score is the exact mean recall probability on a fixed exam day (no sampling noise on the exam).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

LEITNER_BOXES = (1, 2, 4, 8, 16, 32)
FIXED_STEPS = (1, 3, 7)


def next_due_fixed(state: int, grade: int) -> tuple[int, int | None]:
    """State = number of reviews done. Ignores the grade by design."""
    nxt = state + 1
    return nxt, (FIXED_STEPS[nxt] if nxt < len(FIXED_STEPS) else None)


def next_due_leitner(state: int, grade: int) -> tuple[int, int | None]:
    """State = box index. Recalled -> next box, forgot -> back to box 0."""
    box = min(state + 1, len(LEITNER_BOXES) - 1) if grade else 0
    return box, LEITNER_BOXES[box]


LONG_GAP = 14


def next_due_fixed_long(state: int, grade: int) -> tuple[int, int | None]:
    """Fixed 1·3·7, then a review every LONG_GAP days forever: the fair non-adaptive arm for long exams."""
    nxt = state + 1
    return nxt, (FIXED_STEPS[nxt] if nxt < len(FIXED_STEPS) else LONG_GAP)


SCHEDULERS = {
    "fixed": (next_due_fixed, FIXED_STEPS[0]),
    "fixed_long": (next_due_fixed_long, FIXED_STEPS[0]),
    "leitner": (next_due_leitner, LEITNER_BOXES[0]),
}


def recall_prob(model: str, elapsed: np.ndarray | float, strength: np.ndarray | float):
    if model == "exp":
        return np.exp(-np.asarray(elapsed) / strength)
    if model == "power":
        return (1.0 + np.asarray(elapsed) / strength) ** -0.7
    raise ValueError(f"unknown forgetting model {model!r}; use 'exp' or 'power'")


@dataclass(frozen=True)
class Learner:
    model: str
    gain: float = 2.2
    gain_add: float = 1.5
    lapse: float = 0.5


def simulate_run(scheduler: str, learner: Learner, seed: int, *, n_items: int = 30, exam_day: int = 60,
                 daily_budget: int = 4) -> tuple[float, float]:
    """(mean exam recall probability, mean reviews per item). Items are learned on day 0; reviews are capped
    per day (most overdue first)."""
    fn, first_gap = SCHEDULERS[scheduler]
    rng = np.random.default_rng(seed)
    strength = rng.lognormal(np.log(2.0), 0.4, n_items)  # difficulty draw: same for both schedulers
    draws = rng.random((exam_day + 1, n_items))  # recall draws indexed by (day, item): common random numbers
    last = np.zeros(n_items)
    state = np.zeros(n_items, dtype=int)
    due: list[float | None] = [float(first_gap)] * n_items
    reviews = 0
    for day in range(1, exam_day + 1):
        ready = sorted((i for i in range(n_items) if due[i] is not None and due[i] <= day),
                       key=lambda i: due[i])[:daily_budget]
        reviews += len(ready)
        for i in ready:
            ok = draws[day, i] < recall_prob(learner.model, day - last[i], strength[i])
            if ok:
                strength[i] = (strength[i] * learner.gain if learner.model == "exp"
                               else strength[i] * (1.0 + learner.gain_add * min(1.0, (day - last[i]) / strength[i])))
            else:
                strength[i] *= learner.lapse
            last[i] = day
            state[i], gap = fn(int(state[i]), int(ok))
            due[i] = None if gap is None else day + gap
    return float(np.mean(recall_prob(learner.model, exam_day - last, strength))), reviews / n_items


def simulate(*args, **kw) -> float:
    return simulate_run(*args, **kw)[0]


EXAM_DAYS = (14, 60)  # 14: inside the fixed 1·3·7 window; 60: long retention


def seed_rows(seed: int, exam_days: tuple[int, ...] = EXAM_DAYS) -> list[dict]:
    """One seed's table: score and reviews/item per (exam day, model, scheduler). The CI job runs this per seed."""
    rows = []
    for day in exam_days:
        for model in ("exp", "power"):
            for name in SCHEDULERS:
                score, reviews = simulate_run(name, Learner(model), seed, exam_day=day)
                rows.append({"exam_day": day, "model": model, "scheduler": name,
                             "score": score, "reviews_per_item": reviews})
    return rows


def aggregate(rows_by_seed: list[list[dict]]) -> list[dict]:
    """Across seeds: mean/sd of score and reviews, and the paired gain of each other arm over `fixed`.
    `adopt` = gain mean > the larger between-seed sd of the two arms (the #600 rule)."""
    out = []
    keys = sorted({(r["exam_day"], r["model"], r["scheduler"]) for rows in rows_by_seed for r in rows})
    val = {(sd, *k): r for sd, rows in enumerate(rows_by_seed) for r in rows for k in [(r["exam_day"], r["model"], r["scheduler"])]}
    for day, model, name in keys:
        sc = np.array([val[(i, day, model, name)]["score"] for i in range(len(rows_by_seed))])
        rv = np.array([val[(i, day, model, name)]["reviews_per_item"] for i in range(len(rows_by_seed))])
        row = {"exam_day": day, "model": model, "scheduler": name, "score_mean": float(sc.mean()),
               "score_sd": float(sc.std(ddof=1)), "reviews_per_item": float(rv.mean())}
        if name != "fixed":
            base = np.array([val[(i, day, model, "fixed")]["score"] for i in range(len(rows_by_seed))])
            g = sc - base
            row.update({"gain_vs_fixed_mean": float(g.mean()), "gain_vs_fixed_sd": float(g.std(ddof=1)),
                        "adopt": bool(g.mean() > max(sc.std(ddof=1), base.std(ddof=1)))})
        out.append(row)
    return out


def compare(seeds: tuple[int, ...] = tuple(range(8))) -> list[dict]:
    return aggregate([seed_rows(sd) for sd in seeds])


if __name__ == "__main__":
    for r in compare():
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
