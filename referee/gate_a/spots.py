"""Loader for the fixed Gate A spot set; every spot is validated as an `icm_reference.Spot`."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from referee.anchors.icm_reference import Spot, SpotError

SPOT_SET_VERSION = "gate-a-spots-v1"
SPOTS_V1 = Path(__file__).with_name("spots_v1.json")
REQUIRED = ("id", "stacks", "sb", "bb", "ante", "bb_ante", "payouts", "hero", "kind", "players", "bubble")
KINDS = ("push", "call")
PLAYERS = (6, 9)


class SpotSetError(ValueError):
    pass


def load_spots(path: str | Path = SPOTS_V1) -> list[tuple[str, Spot, dict]]:
    """Return [(id, Spot, meta)] with meta = {hero, kind, players, bubble, pusher}; pusher is None for push spots."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out, seen = [], set()
    for i, raw in enumerate(data.get("spots", [])):
        sid = raw.get("id", f"#{i}")
        missing = [k for k in REQUIRED if k not in raw]
        if missing:
            raise SpotSetError(f"spot {sid}: missing {missing}; add the fields to the spot entry.")
        if sid in seen:
            raise SpotSetError(f"duplicate spot id {sid!r}; ids must be unique, rename one.")
        seen.add(sid)
        if raw["kind"] not in KINDS:
            raise SpotSetError(f"spot {sid}: kind {raw['kind']!r} must be one of {KINDS}.")
        if raw["players"] not in PLAYERS:
            raise SpotSetError(f"spot {sid}: players {raw['players']!r} must be one of {PLAYERS}.")
        if len(raw["stacks"]) != raw["players"]:
            raise SpotSetError(f"spot {sid}: players {raw['players']} but {len(raw['stacks'])} stacks; "
                               f"make them equal.")
        try:
            spot = Spot(tuple(raw["stacks"]), raw["sb"], raw["bb"], tuple(raw["payouts"]),
                        raw["ante"], raw["bb_ante"])
        except SpotError as e:
            raise SpotSetError(f"spot {sid}: {e}") from e
        hero = raw["hero"]
        # push needs a first-in seat (not the BB); call needs a seat with an earlier pusher (not the first seat)
        lo, hi = (0, spot.n - 2) if raw["kind"] == "push" else (1, spot.n - 1)
        if isinstance(hero, bool) or not isinstance(hero, int) or not lo <= hero <= hi:
            raise SpotSetError(f"spot {sid}: hero {hero!r} must be a seat in {lo}..{hi} for a "
                               f"{raw['kind']} spot with {spot.n} seats.")
        pusher = raw.get("pusher")
        if raw["kind"] == "call" and (isinstance(pusher, bool) or not isinstance(pusher, int)
                                      or not 0 <= pusher < hero):
            raise SpotSetError(f"spot {sid}: call spot needs integer pusher in 0..{hero - 1} (a seat before "
                               f"hero {hero}); add a 'pusher' field.")
        if raw["kind"] == "push" and pusher is not None:
            raise SpotSetError(f"spot {sid}: push spot must not have 'pusher'; remove it.")
        meta = {k: raw[k] for k in ("hero", "kind", "players", "bubble")}
        out.append((sid, spot, {**meta, "pusher": pusher}))
    return out


def spot_set_hash(path: str | Path = SPOTS_V1) -> tuple[str, str]:
    """(SPOT_SET_VERSION, sha256 of the file bytes)."""
    return SPOT_SET_VERSION, hashlib.sha256(Path(path).read_bytes()).hexdigest()
