"""Agent interface and the information an agent is allowed to see.

An `Observation` is built per decision for exactly one player: it contains that player's own hole
cards and public information only. Other players' hole cards appear solely in SHOWDOWN events.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from stalker.tournament.hand import LegalActions

ActionKind = Literal["fold", "call", "raise"]
EventType = Literal["START_GAME", "NEW_HAND", "ACTION", "SHOWDOWN", "HAND_END", "END_GAME"]


@dataclass(frozen=True)
class Action:
    """`call` also means check. `amount` is the raise-to total for this street (only for `raise`)."""

    kind: ActionKind
    amount: int = 0


@dataclass(frozen=True)
class Event:
    """A public event. `data` holds only information every player at the table may see."""

    type: EventType
    game_id: str
    hand_id: int | None = None
    table_id: int | None = None
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Observation:
    game_id: str
    tournament_id: str
    hand_id: int
    hand_no: int  # round number, 1-based; selects the blind level
    table_id: int
    player_id: int
    seat: int
    button: int
    hole_cards: tuple[str, ...]  # own cards only
    board: tuple[str, ...]
    pot: int
    stacks: dict[int, int]  # seat -> chips behind; only occupied seats at this table
    bets: dict[int, int]  # seat -> chips committed this street
    in_hand: tuple[int, ...]  # seats not yet folded
    seat_players: dict[int, int]  # seat -> player_id
    sb: int
    bb: int
    ante: int
    next_blinds: tuple[int, int, int] | None  # (sb, bb, ante) of the next level, None at the last
    players_remaining: int
    paid_places: int
    legal: LegalActions
    action_history: tuple[tuple[int, str, int], ...]  # public (seat, 'f'|'cc'|'cbr', amount) this hand


class Agent:
    """Base class: override `act`; the other hooks default to no-ops."""

    def on_game_start(self, game_id: str) -> None:
        pass

    def observe(self, event: Event) -> None:
        pass

    def act(self, observation: Observation) -> Action:
        raise NotImplementedError

    def on_game_end(self, game_id: str) -> None:
        pass
