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


SCHEDULERS = {
    "fixed": (next_due_fixed, FIXED_STEPS[0]),
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


def simulate(scheduler: str, learner: Learner, seed: int, *, n_items: int = 30, exam_day: int = 60,
             daily_budget: int = 4) -> float:
    """Mean exam recall probability. Items are learned on day 0; reviews are capped per day (most overdue first)."""
    fn, first_gap = SCHEDULERS[scheduler]
    rng = np.random.default_rng(seed)
    strength = rng.lognormal(np.log(2.0), 0.4, n_items)  # difficulty draw: same for both schedulers
    draws = rng.random((exam_day + 1, n_items))  # recall draws indexed by (day, item): common random numbers
    last = np.zeros(n_items)
    state = np.zeros(n_items, dtype=int)
    due: list[float | None] = [float(first_gap)] * n_items
    for day in range(1, exam_day + 1):
        ready = sorted((i for i in range(n_items) if due[i] is not None and due[i] <= day),
                       key=lambda i: due[i])[:daily_budget]
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
    return float(np.mean(recall_prob(learner.model, exam_day - last, strength)))


def compare(seeds: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7), **kw) -> dict:
    """Per (model, scheduler): mean/sd over seeds, plus paired gain leitner - fixed."""
    out: dict = {}
    for model in ("exp", "power"):
        learner = Learner(model)
        s = {name: np.array([simulate(name, learner, sd, **kw) for sd in seeds]) for name in SCHEDULERS}
        gain = s["leitner"] - s["fixed"]
        out[model] = {
            **{n: {"mean": float(v.mean()), "sd": float(v.std(ddof=1))} for n, v in s.items()},
            "gain_mean": float(gain.mean()), "gain_sd": float(gain.std(ddof=1)),
            "adopt": bool(gain.mean() > max(s["fixed"].std(ddof=1), s["leitner"].std(ddof=1))),
        }
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(compare(), indent=2, ensure_ascii=False))
