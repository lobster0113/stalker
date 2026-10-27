"""Cash-game session engine (`CashSession`): fixed blinds, fixed seats, re-buys and top-ups between hands.

Rules are Gate R cash v1 (`referee/GATES.md`, checked by `referee/gate_r/cash.py`): no rake, no straddle, nobody
joins or leaves, the button moves one seat every hand, a seat that ends a hand with no chips re-buys `buyin`
before the next hand, and with `auto_topup` a seat below `buyin` is filled back to `buyin` (plan §2.4).
Agent `i` sits in seat `i` for the whole session. Hands reuse the tournament hand engines: `FastHand` by default
(about 20x faster; `tests/test_fast_hand.py` holds it to PokerKit), `engine="pokerkit"` for the reference `Hand`.

`CashResult.events` is the session stream in the Gate R format (dicts in order):
  SEAT {seat, amount} | HAND {button, stacks} | HAND_END {stacks} | REBUY {seat, amount, stack} | TOPUP {seat, amount, stack}
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Sequence

import numpy as np

from stalker.agents.base import Action, Agent, Event, Observation
from stalker.tournament.fast_hand import FastHand
from stalker.tournament.hand import Hand

ObserverFn = Callable[[Event], None]
Engine = Literal["fast", "pokerkit"]
_ENGINES = {"fast": FastHand, "pokerkit": Hand}


@dataclass(frozen=True)
class CashConfig:
    name: str
    seats: int
    sb: int
    bb: int
    buyin: int  # initial buy-in and re-buy amount; also the auto top-up target
    hands: int
    min_buyin: int = 0  # 0 = same as buyin
    max_buyin: int = 0  # 0 = same as buyin
    auto_topup: bool = False

    def __post_init__(self) -> None:
        if not 2 <= self.seats <= 9:
            raise ValueError(f"seats must be 2..9, got {self.seats}")
        if not 0 < self.sb <= self.bb:
            raise ValueError("need 0 < sb <= bb")
        if self.hands < 0:
            raise ValueError("hands must be >= 0")
        if not self.buy_range[0] <= self.buyin <= self.buy_range[1]:
            raise ValueError(f"buyin {self.buyin} outside [min_buyin, max_buyin] = {self.buy_range}")

    @property
    def buy_range(self) -> tuple[int, int]:
        return self.min_buyin or self.buyin, self.max_buyin or self.buyin

    @property
    def depth_bb(self) -> float:
        return self.buyin / self.bb


@dataclass(frozen=True)
class CashResult:
    name: str
    hands: int
    bb: int
    start: tuple[int, ...]  # initial buy-in by seat
    rebuys: tuple[int, ...]  # chips re-bought by seat
    topups: tuple[int, ...]  # chips topped up by seat
    final: tuple[int, ...]  # stacks after the last hand
    events: tuple[dict, ...]
    illegal_actions: int  # agent actions replaced by check/fold because they were illegal

    @property
    def net(self) -> tuple[int, ...]:
        """Per-seat result in chips: final - start - rebuys - topups. Sums to 0 (no rake)."""
        return tuple(f - s - r - t for f, s, r, t in zip(self.final, self.start, self.rebuys, self.topups))

    def bb_per_100(self) -> tuple[float, ...]:
        return tuple(bb_per_100(n, self.hands, self.bb) for n in self.net)


def bb_per_100(net_chips: int, hands: int, bb: int) -> float:
    """Win rate in big blinds per 100 hands (Gate Q unit)."""
    if hands <= 0:
        raise ValueError("bb/100 needs hands > 0")
    return net_chips / bb / hands * 100


class CashSession:
    def __init__(self, config: CashConfig, agents: Sequence[Agent], rng: np.random.Generator,
                 observer: ObserverFn | None = None, session_id: str = "cash-0", engine: Engine = "fast") -> None:
        if len(agents) != config.seats:
            raise ValueError(f"need {config.seats} agents (one per seat), got {len(agents)}")
        if engine not in _ENGINES:
            raise ValueError(f"engine must be one of {sorted(_ENGINES)}, got {engine!r}")
        self.hand_cls = _ENGINES[engine]
        self.cfg, self.agents, self.rng, self.observer = config, list(agents), rng, observer
        self.session_id = session_id
        self.illegal = 0

    def _emit(self, event: Event) -> None:
        if self.observer is not None:
            self.observer(event)
        for a in self.agents:
            a.observe(event)

    def run(self) -> CashResult:
        cfg, rng = self.cfg, self.rng
        n = cfg.seats
        events: list[dict] = []
        stacks = [cfg.buyin] * n
        rebuys, topups = [0] * n, [0] * n
        for s in range(n):
            events.append({"type": "SEAT", "seat": s, "amount": cfg.buyin})
        for a in self.agents:
            a.on_game_start(self.session_id)
        button = int(rng.integers(n))
        for hand_no in range(1, cfg.hands + 1):
            if hand_no > 1:
                button = (button + 1) % n
                for s in range(n):
                    if stacks[s] == 0:
                        events.append({"type": "REBUY", "seat": s, "amount": cfg.buyin, "stack": 0})
                        rebuys[s] += cfg.buyin
                        stacks[s] = cfg.buyin
                    elif cfg.auto_topup and stacks[s] < cfg.buyin:
                        amount = cfg.buyin - stacks[s]
                        events.append({"type": "TOPUP", "seat": s, "amount": amount, "stack": stacks[s]})
                        topups[s] += amount
                        stacks[s] = cfg.buyin
            events.append({"type": "HAND", "button": button, "stacks": dict(enumerate(stacks))})
            stacks = self._play_hand(hand_no, button, stacks)
            events.append({"type": "HAND_END", "stacks": dict(enumerate(stacks))})
        for a in self.agents:
            a.on_game_end(self.session_id)
        return CashResult(cfg.name, cfg.hands, cfg.bb, (cfg.buyin,) * n, tuple(rebuys), tuple(topups),
                          tuple(stacks), tuple(events), self.illegal)

    def _play_hand(self, hand_no: int, button: int, stacks: list[int]) -> list[int]:
        cfg = self.cfg
        seat_players = {s: s for s in range(cfg.seats)}
        start = dict(enumerate(stacks))
        hand = self.hand_cls(stacks, button, cfg.sb, cfg.bb, self.rng)
        holes = {s: tuple(hand.hole_cards(s)) for s in seat_players}
        self._emit(Event("NEW_HAND", self.session_id, hand_no, 0, {
            "hand_no": hand_no, "button": button, "seat_players": dict(seat_players), "stacks": dict(start),
            "sb": cfg.sb, "bb": cfg.bb, "ante": 0}))
        folded: set[int] = set()
        while not hand.is_over:
            la = hand.legal_actions()
            seat = la.seat
            obs = Observation(
                game_id=self.session_id, tournament_id=cfg.name, hand_id=hand_no, hand_no=hand_no, table_id=0,
                player_id=seat, seat=seat, button=button, hole_cards=holes[seat], board=tuple(hand.board()),
                pot=hand.pot, stacks=hand.stacks, bets=hand.bets,
                in_hand=tuple(s for s in hand.seats if s not in folded), seat_players=dict(seat_players),
                sb=cfg.sb, bb=cfg.bb, ante=0, next_blinds=None, players_remaining=cfg.seats, paid_places=0,
                legal=la, action_history=tuple(hand.actions()), all_stacks=tuple(sorted(stacks, reverse=True)),
                hand_start_stack=start[seat], ante_mode="none")
            street = len(hand.board())
            kind = self._apply(hand, la, self.agents[seat].act(obs))
            if kind[0] == "fold":
                folded.add(seat)
            self._emit(Event("ACTION", self.session_id, hand_no, 0, {
                "seat": seat, "player_id": seat, "action": kind[0], "amount": kind[1],
                "pot": hand.pot, "street": street, "facing_bet": la.call_amount > 0}))
        alive = [s for s in seat_players if s not in folded]
        if len(alive) > 1:
            self._emit(Event("SHOWDOWN", self.session_id, hand_no, 0, {
                "board": tuple(hand.board()), "hands": {s: holes[s] for s in alive}}))
        res = hand.result()
        self._emit(Event("HAND_END", self.session_id, hand_no, 0, {
            "final_stacks": dict(enumerate(res.final_stacks)), "deltas": dict(enumerate(res.deltas))}))
        return list(res.final_stacks)

    def _apply(self, hand: Hand | FastHand, la, action: Action) -> tuple[str, int]:
        """Apply `action`, falling back to check/fold when it is illegal (as the tournament director)."""
        if action.kind == "fold" and la.can_fold:
            hand.fold()
            return "fold", 0
        if action.kind == "call":
            hand.check_or_call()
            return "call", la.call_amount
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


def run_cash_session(config: CashConfig, agents: Sequence[Agent], rng: np.random.Generator,
                     observer: ObserverFn | None = None, session_id: str = "cash-0",
                     engine: Engine = "fast") -> CashResult:
    return CashSession(config, agents, rng, observer, session_id, engine).run()
