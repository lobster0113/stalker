"""Gate T3 (format): every TP value fits the spec's scale, the N/A rules and the tier's item list (referee/GATES.md Gate T).

Checked per decision and per tier, on the T4 spot observations plus the T1 recorded-game decisions:
- scale: `0-100` and `range_169` cells are integers in 0..100 (range_169 has 169 cells), `risk_premium_pp`
  is a finite number in -100..100. The step grid of a tier (beginner 25, mid 10) is what the screen offers
  the person; the policy's own vector only needs whole-number cells.
- N/A: an item that `stalker.tp.reference.not_applicable` rules out for this decision has no value.
- tier: an item the tier does not ask (`spec.tier_items`) has no value.
The N/A inputs are the ones public information gives (street, opponent count, legal actions); the
per-opponent opportunity counts and 'opponent bet this street' are not in the public observation yet.
Agents expose `tp(po)` returning a mapping item -> value (None = no value); `tp(po, tier)` is used if accepted.
"""
from __future__ import annotations

import math

from referee.gate_t.t4 import load as load_t4, observation
from stalker.env.contract import PublicObservation, decision_context
from stalker.tp.reference import not_applicable
from stalker.tp.spec import TIER_ORDER, load

RANGE_CELLS = 169


def _context(po: PublicObservation) -> dict:
    dc = decision_context(po)
    return {"street": dc.street, "opponents": sum(1 for k, s in enumerate(po.seats) if k and s.used and s.in_hand),
            "bet_or_raise_legal": "raise" in dc.legal_actions, "game": "tournament",
            "call_or_all_in": dc.to_call > 0 or dc.all_in}


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) or (isinstance(x, float) and x.is_integer())


def _scale_error(scale: str, v) -> str | None:
    cells = list(v) if isinstance(v, (list, tuple)) else [v]
    if scale == "range_169":
        if len(cells) != RANGE_CELLS:
            return f"needs {RANGE_CELLS} cells, got {len(cells)}"
    elif len(cells) != 1 or isinstance(v, (list, tuple)):
        return "needs a single value"
    lo, hi = (-100, 100) if scale == "risk_premium_pp" else (0, 100)
    for x in cells:
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            return f"value {x!r} is not a finite number"
        if not lo <= x <= hi:
            return f"value {x!r} outside {lo}..{hi}"
        if scale != "risk_premium_pp" and not _is_int(x):
            return f"value {x!r} is not a whole number (scale {scale})"
    return None


def decision_errors(spec, values: dict, tier: str, po: PublicObservation) -> list[str]:
    ctx, asked, errs = _context(po), set(spec.tier_items(tier)), []
    for item, v in values.items():
        if v is None:
            continue
        if item not in spec.item_ids:
            errs.append(f"{item}: not a TP item of spec {spec.version}")
            continue
        if item not in asked:
            errs.append(f"{item}: has a value but tier {tier} does not ask it")
        why = not_applicable(item, ctx, {})
        if why:
            errs.append(f"{item}: has a value but is N/A here ({why})")
        bad = _scale_error(spec.item(item)["scale"], v)
        if bad:
            errs.append(f"{item}: {bad}")
    return errs


def _observations() -> list[PublicObservation]:
    from referee.gate_t import _observations as recorded

    out = recorded()
    for p in load_t4()[0]:
        for side in ("a", "b"):
            obs, builder = observation(p[side])
            out.append(builder.build(obs))
    return out


def _values(agent, po: PublicObservation, tier: str):
    try:
        return agent.tp(po, tier)
    except TypeError:
        return agent.tp(po)


def check_t3(agent) -> tuple[int, int, list[str]]:
    """Returns (passed, total, failures). One check per (decision, tier)."""
    spec, passed, total, failures = load(), 0, 0, []
    for n, po in enumerate(_observations()):
        for tier in TIER_ORDER:
            total += 1
            errs = decision_errors(spec, dict(_values(agent, po, tier)), tier, po)
            if errs:
                failures.append(f"T3: decision {n} tier {tier}: " + "; ".join(errs[:3])
                                + ". Fix the TP head so values follow docs/TP.md §3-§4.1 (stalker/tp/spec/).")
            else:
                passed += 1
    return passed, total, failures
