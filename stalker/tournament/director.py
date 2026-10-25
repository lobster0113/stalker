"""Tournament director: runs a whole game (seating, blind levels, busts, balancing, payouts).

Conventions:
- All tables play exactly one hand per *round*; `hand_no` (selects the blind level) is the round number.
  There is no hand-for-hand mode, so bubble play is not special-cased.
- Several players busting in the same round are ranked by chips at the start of their hand (more chips =
  better place); equal starting stacks are ordered by a draw from the injected rng (reproducible).
- Tables are broken as soon as fewer tables can seat everyone, then balanced to a spread of at most 1.
  A moved player takes a random empty seat. The button advances to the next occupied seat each hand
  (no dead button).
- A seat's hole cards become public only in SHOWDOWN (every player still in the hand when it ends with
  two or more players left); folded or won-uncontested cards are never revealed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

from stalker.agents.base import Action, Agent, Event, Observation
from stalker.tournament.config import ConfigError, TournamentConfig
from stalker.tournament.hand import Hand

MAX_ROUNDS = 100_000

ObserverFn = Callable[[Event], None]


@dataclass(frozen=True)
class GameResult:
    game_id: str
    tournament_id: str
    ranks: tuple[int, ...]  # by player_id, 1 = winner
    prizes: tuple[float, ...]  # by player_id, in currency units (0 outside the paid places)
    hands: int  # hands dealt over all tables
    rounds: int
    illegal_actions: int  # agent actions replaced by check/fold because they were illegal


def rank_busts(busted: Sequence[tuple[int, int]], rng: np.random.Generator) -> list[int]:
    """Order simultaneous busts best first. `busted` = (player_id, chips at start of the hand)."""
    shuffled = [busted[i] for i in rng.permutation(len(busted))]  # random tie-break, then stable sort
    shuffled.sort(key=lambda b: -b[1])
    return [p for p, _ in shuffled]


class _Table:
    def __init__(self, table_id: int, size: int, button: int) -> None:
        self.id = table_id
        self.seats: list[int | None] = [None] * size
        self.button = button

    @property
    def players(self) -> list[int]:
        return [p for p in self.seats if p is not None]

    def empty_seats(self) -> list[int]:
        return [s for s, p in enumerate(self.seats) if p is None]

    def next_button(self) -> int:
        n = len(self.seats)
        for k in range(1, n + 1):
            s = (self.button + k) % n
            if self.seats[s] is not None:
                return s
        raise RuntimeError("table has no players")


class _Game:
    def __init__(self, config: TournamentConfig, agents: Sequence[Agent], rng: np.random.Generator,
                 observer: ObserverFn | None, game_id: str, tournament_id: str) -> None:
        if len(agents) != config.players:
            raise ValueError(f"need {config.players} agents (one per player), got {len(agents)}")
        if config.length_unit != "hands":
            raise ConfigError("director supports length_unit='hands' only; time-based levels are not implemented.")
        if config.short_stack_rule != "all_in":
            raise ConfigError("director supports short_stack_rule='all_in' only; 'skip' is not implemented.")
        self.cfg, self.agents, self.rng, self.observer = config, list(agents), rng, observer
        self.game_id, self.tournament_id = game_id, tournament_id
        self.stacks = {p: config.starting_stack for p in range(config.players)}
        self.ranks: dict[int, int] = {}
        self.hand_id = 0
        self.illegal = 0
        self.round_stacks: tuple[int, ...] = ()
        self.tables: dict[int, _Table] = {}
        self._next_table_id = 0
        self._seat_initial()

    # ---- seating ----
    def _new_table(self) -> _Table:
        t = _Table(self._next_table_id, self.cfg.table_size, int(self.rng.integers(self.cfg.table_size)))
        self._next_table_id += 1
        self.tables[t.id] = t
        return t

    def _sit(self, table: _Table, player: int) -> None:
        free = table.empty_seats()
        table.seats[free[int(self.rng.integers(len(free)))]] = player

    def _seat_initial(self) -> None:
        order = [int(p) for p in self.rng.permutation(self.cfg.players)]
        n_tables = math.ceil(self.cfg.players / self.cfg.table_size)
        for i in range(n_tables):
            table = self._new_table()
            for p in order[i::n_tables]:
                self._sit(table, p)

    def _rebalance(self) -> None:
        alive = len(self.stacks)
        want = max(1, math.ceil(alive / self.cfg.table_size))
        while len(self.tables) > want:
            broken = min(self.tables.values(), key=lambda t: (len(t.players), t.id))
            del self.tables[broken.id]
            for p in broken.players:
                dest = min((t for t in self.tables.values() if t.empty_seats()), key=lambda t: (len(t.players), t.id))
                self._sit(dest, p)
        while True:
            by_size = sorted(self.tables.values(), key=lambda t: (len(t.players), t.id))
            small, large = by_size[0], by_size[-1]
            if len(large.players) - len(small.players) <= 1:
                return
            mover = large.players[int(self.rng.integers(len(large.players)))]
            large.seats[large.seats.index(mover)] = None
            self._sit(small, mover)

    # ---- events ----
    def _emit(self, event: Event, table: _Table | None) -> None:
        if self.observer is not None:
            self.observer(event)
        if table is not None:
            for p in table.players:
                self.agents[p].observe(event)

    # ---- one hand ----
    def _play_hand(self, table: _Table, hand_no: int) -> list[tuple[int, int]]:
        """Play one hand; return (player_id, start stack) of players who busted."""
        cfg = self.cfg
        level = cfg.level_at(hand_no)
        nxt = cfg.next_level(hand_no)
        self.hand_id += 1
        hand_id = self.hand_id
        table.button = table.next_button()
        seat_players = {s: p for s, p in enumerate(table.seats) if p is not None}
        start = {s: self.stacks[p] for s, p in seat_players.items()}
        ante_mode = cfg.ante_mode if level.ante else "none"
        hand = Hand([start.get(s, 0) for s in range(len(table.seats))], table.button, level.sb, level.bb,
                    self.rng, ante=level.ante, ante_mode=ante_mode)
        holes = {s: tuple(hand.hole_cards(s)) for s in seat_players}
        self._emit(Event("NEW_HAND", self.game_id, hand_id, table.id, {
            "hand_no": hand_no, "button": table.button, "seat_players": dict(seat_players), "stacks": dict(start),
            "sb": level.sb, "bb": level.bb, "ante": level.ante}), table)

        folded: set[int] = set()
        while not hand.is_over:
            la = hand.legal_actions()
            seat = la.seat
            agent = self.agents[seat_players[seat]]
            st = hand.state
            bets = {hand.seats[i]: b for i, b in enumerate(st.bets)}
            obs = Observation(
                game_id=self.game_id, tournament_id=self.tournament_id, hand_id=hand_id, hand_no=hand_no,
                table_id=table.id, player_id=seat_players[seat], seat=seat, button=table.button,
                hole_cards=holes[seat], board=tuple(hand.board()), pot=st.total_pot_amount,
                stacks={hand.seats[i]: s for i, s in enumerate(st.stacks)}, bets=bets,
                in_hand=tuple(s for s in hand.seats if s not in folded), seat_players=dict(seat_players),
                sb=level.sb, bb=level.bb, ante=level.ante,
                next_blinds=None if nxt is None else (nxt.sb, nxt.bb, nxt.ante),
                players_remaining=len(self.stacks), paid_places=len(cfg.payouts), legal=la,
                action_history=tuple(hand.actions()), all_stacks=self.round_stacks,
                hand_start_stack=start[seat],
                ante_mode=ante_mode, action_order=self._action_order(hand, folded, seat))
            action = agent.act(obs)
            street = len(hand.board())  # 0/3/4/5 board cards = preflop/flop/turn/river
            kind = self._apply(hand, la, action)
            if kind[0] == "fold":
                folded.add(seat)
            self._emit(Event("ACTION", self.game_id, hand_id, table.id, {
                "seat": seat, "player_id": seat_players[seat], "action": kind[0], "amount": kind[1],
                "pot": hand.state.total_pot_amount, "street": street, "facing_bet": la.call_amount > 0}), table)

        alive_seats = [s for s in seat_players if s not in folded]
        if len(alive_seats) > 1:
            self._emit(Event("SHOWDOWN", self.game_id, hand_id, table.id, {
                "board": tuple(hand.board()), "hands": {s: holes[s] for s in alive_seats}}), table)
        res = hand.result()
        busted = []
        for s, p in seat_players.items():
            self.stacks[p] = res.final_stacks[s]
        self._emit(Event("HAND_END", self.game_id, hand_id, table.id, {
            "final_stacks": {s: res.final_stacks[s] for s in seat_players},
            "deltas": {s: res.deltas[s] for s in seat_players}}), table)
        for s, p in seat_players.items():
            if res.final_stacks[s] == 0:
                busted.append((p, start[s]))
                table.seats[s] = None
        return busted

    @staticmethod
    def _action_order(hand: Hand, folded: set[int], actor: int) -> tuple[int, ...]:
        """Seats that can still act this street (not folded, not all-in), from `actor` around the table."""
        seats = hand.seats  # clockwise from the seat after the button
        live = [s for i, s in enumerate(seats) if s not in folded and hand.state.stacks[i] > 0]
        k = live.index(actor)
        return tuple(live[k:] + live[:k])

    def _apply(self, hand: Hand, la, action: Action) -> tuple[str, int]:
        """Apply `action`, falling back to check/fold when it is illegal. Returns (kind, chips)."""
        if action.kind == "fold" and la.can_fold:
            hand.fold()
            return "fold", 0
        if action.kind == "call":
            amount = la.call_amount
            hand.check_or_call()
            return "call", amount
        if (action.kind == "raise" and la.min_raise_to is not None
                and isinstance(action.amount, int) and la.min_raise_to <= action.amount <= la.max_raise_to):
            hand.raise_to(action.amount)
            return "raise", action.amount
        self.illegal += 1
        if la.call_amount == 0 or not la.can_fold:
            hand.check_or_call()
            return "call", la.call_amount
        hand.fold()
        return "fold", 0

    # ---- game ----
    def run(self) -> GameResult:
        total = self.cfg.starting_stack * self.cfg.players
        for a in self.agents:
            a.on_game_start(self.game_id)
        self._emit(Event("START_GAME", self.game_id, data={
            "tournament_id": self.tournament_id, "players": self.cfg.players, "table_size": self.cfg.table_size}), None)
        hand_no = 0
        while len(self.stacks) > 1:
            hand_no += 1
            if hand_no > MAX_ROUNDS:
                raise RuntimeError(f"game exceeded {MAX_ROUNDS} rounds; agents never bust each other out")
            busted: list[tuple[int, int]] = []
            self.round_stacks = tuple(sorted(self.stacks.values(), reverse=True))
            for table in sorted(self.tables.values(), key=lambda t: t.id):
                busted += self._play_hand(table, hand_no)
            if sum(self.stacks.values()) != total:
                raise RuntimeError(f"chip conservation violated in round {hand_no}")
            place = len(self.stacks) - len(busted) + 1  # best of the busted takes the highest remaining place
            for p in rank_busts(busted, self.rng):
                self.ranks[p] = place
                place += 1
                del self.stacks[p]
            if len(self.stacks) > 1:
                self._rebalance()
        (winner,) = self.stacks
        self.ranks[winner] = 1
        amounts = self.cfg.payout_amounts()
        prizes = tuple(float(amounts[self.ranks[p] - 1]) if self.ranks[p] <= len(amounts) else 0.0
                       for p in range(self.cfg.players))
        self._emit(Event("END_GAME", self.game_id, data={
            "ranks": {p: self.ranks[p] for p in range(self.cfg.players)}}), None)
        for a in self.agents:
            a.on_game_end(self.game_id)
        return GameResult(self.game_id, self.tournament_id, tuple(self.ranks[p] for p in range(self.cfg.players)),
                          prizes, self.hand_id, hand_no, self.illegal)


def run_game(config: TournamentConfig, agents: Sequence[Agent], rng: np.random.Generator,
             observer: ObserverFn | None = None, game_id: str = "game-0",
             tournament_id: str | None = None) -> GameResult:
    """Play one full tournament. `agents[i]` is player_id i. `observer` sees every public event."""
    return _Game(config, agents, rng, observer, game_id, tournament_id or config.name).run()
