"""Difficulty ladder 1..19 over the rule-based persona bots (`stalker.agents.persona`, ADR 0010).

One axis, straight line: level 1 is the calling station (loose, never raises, never folds) and level 19 the
high-stakes pro (tight-aggressive, folds weak hands to bets). Every level interpolates all four parameters
linearly between those two presets, so style and strength both change smoothly and the ladder is deterministic.
Only the endpoints are claimed to be ordered by strength; adjacent levels are not guaranteed (see the research note).
"""
from __future__ import annotations

from stalker.agents.persona import PersonaParams, persona_params

MIN_LEVEL, MAX_LEVEL = 1, 19
_WEAK, _STRONG = "calling_station", "high_stakes_pro"


def level(n: int) -> PersonaParams:
    if isinstance(n, bool) or not isinstance(n, int) or not MIN_LEVEL <= n <= MAX_LEVEL:
        raise ValueError(f"persona level must be an int in {MIN_LEVEL}..{MAX_LEVEL}, got {n!r}")
    t = (n - MIN_LEVEL) / (MAX_LEVEL - MIN_LEVEL)
    a, b = persona_params(_WEAK), persona_params(_STRONG)
    return PersonaParams(*(round(x + (y - x) * t, 4) for x, y in zip(
        (a.vpip, a.pfr, a.aggression, a.fold_to_bet), (b.vpip, b.pfr, b.aggression, b.fold_to_bet))))


def ladder() -> dict[int, PersonaParams]:
    return {n: level(n) for n in range(MIN_LEVEL, MAX_LEVEL + 1)}
