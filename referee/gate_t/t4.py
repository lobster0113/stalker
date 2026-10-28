"""Gate T4 (sufficiency): spot pairs the action head's input must tell apart (referee/GATES.md Gate T).

T1-T3 check that the bottleneck is obeyed; T4 checks that it carries enough. Each pair in
`t4_spots_v1.json` differs in one decision-relevant public fact; its `differs` lists the DecisionContext
fields that fact changes (the fact plus its rule consequences), and tests check the actual difference is
exactly that set. Both spots are turned into real
engine `Observation`s, built into `PublicObservation`s, and the action-head input
(TP vector from the agent's head + DecisionContext) must differ between the two.

Spot fields (chips in big blinds; seats are table seats 0..n-1):
  preset, hero_seat, button, stacks_bb {seat: bb}, in_hand [seats], bets_bb {seat: bb},
  pot_bb, hole, board, history [[seat, "f"|"cc"|"cbr", bb]], players_remaining, paid_places,
  can_raise, all_stacks_bb [bb...], hand_no
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stalker.agents.base import Observation
from stalker.env.contract import decision_context
from stalker.observe.builder import ObservationBuilder
from stalker.tournament.config import load_preset
from stalker.tournament.hand import LegalActions

SPOTS_V1 = Path(__file__).resolve().parent / "t4_spots_v1.json"
MIN_PAIRS = 20
BB = 100
SPOT_KEYS = {"preset", "hero_seat", "button", "stacks_bb", "in_hand", "bets_bb", "pot_bb", "hole", "board",
             "history", "players_remaining", "paid_places", "can_raise", "all_stacks_bb", "hand_no"}


class SpotError(ValueError):
    pass


def load(path: Path = SPOTS_V1) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    pairs = data.get("pairs", [])
    if len(pairs) < MIN_PAIRS:
        raise SpotError(f"{path.name}: {len(pairs)} pairs; Gate T4 needs at least {MIN_PAIRS}")
    ids = [p.get("id") for p in pairs]
    if len(set(ids)) != len(ids):
        raise SpotError(f"{path.name}: duplicate pair ids")
    for p in pairs:
        if not p.get("why"):
            raise SpotError(f"{path.name}: pair {p.get('id')!r} needs a one-line 'why'")
        if not p.get("differs"):
            raise SpotError(f"{path.name}: pair {p.get('id')!r} needs 'differs' (the DecisionContext fields it changes)")
        for side in ("a", "b"):
            unknown = set(p[side]) - SPOT_KEYS
            if unknown:
                raise SpotError(f"{path.name}: pair {p['id']!r} side {side} has unknown keys {sorted(unknown)}")
    return pairs, hashlib.sha256(raw).hexdigest()


def _cards(s: str) -> tuple[str, ...]:
    return tuple(s[i:i + 2] for i in range(0, len(s), 2))


def observation(spot: dict) -> tuple[Observation, ObservationBuilder]:
    cfg = load_preset(spot.get("preset", "6max_sng_wta"))
    stacks = {int(k): int(round(v * BB)) for k, v in spot["stacks_bb"].items()}
    bets = {int(k): int(round(v * BB)) for k, v in spot.get("bets_bb", {}).items()}
    hero = spot["hero_seat"]
    to_call = max(bets.values(), default=0) - bets.get(hero, 0)
    to_call = min(to_call, stacks[hero])
    max_to = bets.get(hero, 0) + stacks[hero]
    can_raise = spot.get("can_raise", True) and stacks[hero] > to_call
    legal = LegalActions(hero, to_call > 0, to_call,
                         min(max(bets.values(), default=0) + BB, max_to) if can_raise else None,
                         max_to if can_raise else None)
    all_stacks = tuple(sorted((int(round(x * BB)) for x in spot.get("all_stacks_bb", spot["stacks_bb"].values())),
                              reverse=True))
    obs = Observation(
        game_id="t4", tournament_id="t4", hand_id=1, hand_no=spot.get("hand_no", 1), table_id=0, player_id=hero,
        seat=hero, button=spot["button"], hole_cards=_cards(spot["hole"]), board=_cards(spot.get("board", "")),
        pot=int(round(spot["pot_bb"] * BB)), stacks=stacks, bets=bets,
        in_hand=tuple(spot.get("in_hand", sorted(stacks))), seat_players={s: s for s in stacks},
        sb=BB // 2, bb=BB, ante=0, next_blinds=None,
        players_remaining=spot.get("players_remaining", len(stacks)), paid_places=spot.get("paid_places", 1),
        legal=legal, action_history=tuple((s, a, int(round(x * BB))) for s, a, x in spot.get("history", [])),
        all_stacks=all_stacks, hand_start_stack=stacks[hero] + bets.get(hero, 0))
    return obs, ObservationBuilder(cfg)


def head_input(agent, spot: dict) -> str:
    """What the action head sees for this spot: TP vector + DecisionContext, as a comparable string."""
    obs, builder = observation(spot)
    po = builder.build(obs)
    return repr((sorted(agent.tp(po).items()), decision_context(po)))


def check_t4(agent, input_fn=head_input, path: Path = SPOTS_V1) -> tuple[int, int, list[str]]:
    pairs, _ = load(path)
    fails = [f"T4: pair {p['id']}: the action head gets the same input for both spots ({p['why']}). "
             "Add the missing fact to the TP or DecisionContext (docs/TP.md §1.1)."
             for p in pairs if input_fn(agent, p["a"]) == input_fn(agent, p["b"])]
    return len(pairs) - len(fails), len(pairs), fails
