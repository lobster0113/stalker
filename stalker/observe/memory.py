"""Game Memory Store: what one player has seen of the *current* game's public events, and nothing else.

Boundary (ADR 0003): memory is keyed by `game_id`, created by `start_game`, destroyed by `end_game`.
`NEW_HAND` only resets per-hand scratch state. Any event or lookup carrying another `game_id` raises
`MemoryBoundaryError`. A player who joins mid-game calls `start_game` late and so only remembers
events from then on. Only public events are accepted: hole cards enter solely through SHOWDOWN.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from stalker.agents.base import Event

CONTEXTS = ("pre_open", "pre_facing", "post_open", "post_facing")
ACTIONS = ("f", "c", "r")  # fold / call(check) / raise


class MemoryBoundaryError(RuntimeError):
    """Raised when memory would cross a game boundary; the message says which game ids clashed."""


@dataclass
class OpponentStats:
    hands: int = 0  # hands dealt while seated at the observed table
    opportunities: dict[str, int] = field(default_factory=lambda: {c: 0 for c in CONTEXTS})
    actions: dict[str, dict[str, int]] = field(default_factory=lambda: {c: {a: 0 for a in ACTIONS} for c in CONTEXTS})
    vpip_hands: int = 0  # hands with a voluntary preflop call/raise (calling a bet counts; checking the BB does not)
    pfr_hands: int = 0
    showdowns: int = 0


@dataclass(frozen=True)
class PublicAction:
    hand_id: int
    player_id: int
    street: int
    action: str  # 'f' | 'c' | 'r'
    amount: int


@dataclass(frozen=True)
class ShowdownRecord:
    hand_id: int
    player_id: int
    hole_cards: tuple[str, ...]
    board: tuple[str, ...]


@dataclass
class GameMemory:
    game_id: str
    recent_actions: deque
    opponents: dict[int, OpponentStats] = field(default_factory=dict)
    showdowns: list[ShowdownRecord] = field(default_factory=list)
    hands_seen: int = 0

    def stats(self, player_id: int) -> OpponentStats:
        return self.opponents.setdefault(player_id, OpponentStats())


class GameMemoryStore:
    """One player's memory. `observe` takes the events that player's agent receives."""

    def __init__(self, recent_k: int = 32) -> None:
        if recent_k < 1:
            raise ValueError("recent_k must be >= 1.")
        self.recent_k = recent_k
        self._mem: GameMemory | None = None
        self._seat_players: dict[int, int] = {}
        self._hand_id: int | None = None
        self._vpip: set[int] = set()
        self._pfr: set[int] = set()

    @property
    def game_id(self) -> str | None:
        return None if self._mem is None else self._mem.game_id

    def start_game(self, game_id: str) -> GameMemory:
        if self._mem is not None:
            raise MemoryBoundaryError(
                f"game {self._mem.game_id!r} is still active; call end_game before start_game({game_id!r}).")
        self._mem = GameMemory(game_id, deque(maxlen=self.recent_k))
        self._seat_players, self._hand_id = {}, None
        return self._mem

    def end_game(self, game_id: str) -> None:
        self._check(game_id)
        self._mem = None
        self._seat_players, self._hand_id = {}, None
        self._vpip, self._pfr = set(), set()

    def get(self, game_id: str) -> GameMemory:
        return self._check(game_id)

    def _check(self, game_id: str) -> GameMemory:
        if self._mem is None:
            raise MemoryBoundaryError(f"no active game; call start_game({game_id!r}) first.")
        if game_id != self._mem.game_id:
            raise MemoryBoundaryError(f"memory belongs to game {self._mem.game_id!r}, not {game_id!r}.")
        return self._mem

    def observe(self, event: Event) -> None:
        mem = self._check(event.game_id)
        d = event.data
        if event.type == "NEW_HAND":
            self._flush_hand(mem)
            self._hand_id = event.hand_id
            self._seat_players = dict(d["seat_players"])
            self._vpip, self._pfr = set(), set()
            mem.hands_seen += 1
            for p in self._seat_players.values():
                mem.stats(p).hands += 1
        elif event.type == "ACTION":
            p, a, street = d["player_id"], d["action"][0], d["street"]
            ctx = ("pre" if street == 0 else "post") + ("_facing" if d["facing_bet"] else "_open")
            st = mem.stats(p)
            st.opportunities[ctx] += 1
            st.actions[ctx][a] += 1
            if street == 0 and (a == "r" or (a == "c" and d["facing_bet"])):
                self._vpip.add(p)
            if street == 0 and a == "r":
                self._pfr.add(p)
            mem.recent_actions.append(PublicAction(event.hand_id, p, street, a, d["amount"]))
        elif event.type == "SHOWDOWN":
            for seat, cards in d["hands"].items():
                p = self._seat_players[seat]
                mem.stats(p).showdowns += 1
                mem.showdowns.append(ShowdownRecord(event.hand_id, p, tuple(cards), tuple(d["board"])))
        elif event.type == "HAND_END":
            self._flush_hand(mem)

    def _flush_hand(self, mem: GameMemory) -> None:
        for p in self._vpip:
            mem.stats(p).vpip_hands += 1
        for p in self._pfr:
            mem.stats(p).pfr_hands += 1
        self._vpip, self._pfr = set(), set()
