"""Gate R: replay a tournament's public event stream with an independent rules model and tally checks.

The model below re-derives postings, action order, bet sizes, uncalled refunds and settlement from the rules
alone (no PokerKit, no `stalker.tournament.hand`) and compares every engine-reported fact against it.
Rules not obvious from a textbook (they follow ADR 0005, which records the engine's tournament rules):
- Antes are posted before blinds; a blind is capped by the stack left after the ante. Heads-up the button
  posts the SB and the other seat the BB (and the BB ante). Short stacks post what they have and are all-in.
- short_stack_rule='skip' (3+ seats): seats starting the hand with fewer than bb + ante chips post no blind;
  SB and BB go to the first two seats, clockwise from left of the button, that have at least that many
  (fewer than two such seats: the all-in postings above).
- Preflop the seat left of the BB acts first; later streets start left of the button.
- When betting opens on a street, a seat that no opponent can bet beyond (every other live seat's bet + stack
  <= its bet) does not act on that street unless someone raises.
- Minimum raise increment = max(1 BB, largest raise increment of the street). A raise below it is legal only
  as an all-in (own stack, or the largest stack any opponent can still match).
- Reopening: a raise at least as large as the street's largest raise so far is full (the street's first bet or
  raise always is, since that largest starts at 0). After a short all-in raise, seats that acted since the last
  full raise may only call or fold until consecutive short all-ins add up to a full raise.
- Uncalled chips above the second-largest bet are returned at the end of each street.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from referee.gate_r.evaluator import strength
from referee.gate_r.settlement import settle

ITEMS = (
    "antes_blinds",       # blind schedule per level, ante mode, postings incl. short-stack exceptions
    "action_order",       # who acts next (positions, heads-up button = SB, skipped all-in seats)
    "bet_sizing",         # call amounts, minimum raise, raise rights after short all-ins
    "street_flow",        # street of each action, showdown participants, full board
    "settlement",         # HAND_END stacks == independent side-pot settlement, chip for chip
    "chip_conservation",  # per hand deltas sum to 0, per round total chips constant
    "button",             # button moves to the next occupied seat
    "stack_continuity",   # a player's stack carries over between hands; busted players never return
    "elimination",        # bust places, simultaneous-bust order, exactly one winner
    "prizes",             # prize per place matches payouts, sum = prize pool
)

_BOARD_LEN = (0, 3, 4, 5)


@dataclass
class Tally:
    counts: dict[str, list[int]] = field(default_factory=lambda: {k: [0, 0] for k in ITEMS})
    failures: list[str] = field(default_factory=list)
    max_failures: int = 20

    def check(self, item: str, ok: bool, msg: str = "") -> bool:
        c = self.counts[item]
        c[1] += 1
        if ok:
            c[0] += 1
        elif len(self.failures) < self.max_failures:
            self.failures.append(f"{item}: {msg}")
        return ok

    @property
    def passed(self) -> int:
        return sum(p for p, _ in self.counts.values())

    @property
    def total(self) -> int:
        return sum(t for _, t in self.counts.values())

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def merge(self, other: "Tally") -> None:
        for k, (p, t) in other.counts.items():
            self.counts[k][0] += p
            self.counts[k][1] += t
        room = self.max_failures - len(self.failures)
        self.failures.extend(other.failures[:max(room, 0)])


class _HandModel:
    """Independent state of one hand, advanced by ACTION events."""

    def __init__(self, cfg, d: dict, tally: Tally, where: str) -> None:
        self.tally, self.where = tally, where
        t = cfg.table_size
        occupied = set(d["seat_players"])
        self.order = [(d["button"] + k) % t for k in range(1, t + 1) if (d["button"] + k) % t in occupied]
        n = len(self.order)
        able = [s for s in self.order if d["stacks"][s] >= d["bb"] + d["ante"]]
        if n == 2:
            self.sb_seat, self.bb_seat = d["button"], self.order[0]
        elif getattr(cfg, "short_stack_rule", "all_in") == "skip" and len(able) >= 2:
            self.sb_seat, self.bb_seat = able[0], able[1]
        else:
            self.sb_seat, self.bb_seat = self.order[0], self.order[1]
        self.stack = dict(d["stacks"])
        self.antes = {s: 0 for s in self.order}
        mode = cfg.ante_mode if d["ante"] else "none"
        for s in (self.order if mode == "classic" else [self.bb_seat] if mode == "bb_ante" else []):
            self.antes[s] = min(d["ante"], self.stack[s])
            self.stack[s] -= self.antes[s]
        self.paid = dict(self.antes)
        self.bet = {s: 0 for s in self.order}
        for s, blind in ((self.sb_seat, d["sb"]), (self.bb_seat, d["bb"])):
            self._put(s, min(blind, self.stack[s]))
        self.bb = d["bb"]
        self.folded: set[int] = set()
        self.street = 0
        self.over = False
        self._begin_street(preflop=True)

    def _put(self, s: int, chips: int) -> None:
        self.stack[s] -= chips
        self.bet[s] += chips
        self.paid[s] += chips

    @property
    def live(self) -> list[int]:
        return [s for s in self.order if s not in self.folded]

    def _begin_street(self, preflop: bool = False) -> None:
        self.acted: set[int] = set()
        self.closed: set[int] = set()  # seats that acted since the last full raise
        self.full_inc = 0  # largest raise increment this street
        self.short_sum = 0  # consecutive short all-in increments since the last full raise
        self.max_bet = max(self.bet.values())
        # fixed when betting opens: a seat no opponent can bet beyond does not act unless raised
        self.sits_out = {s for s in self.order
                         if not any(self.bet[o] + self.stack[o] > self.bet[s] for o in self.live if o != s)}
        self.last = self.bb_seat if preflop else self.order[-1]  # order[-1] is the button
        self._advance()

    def _needs_action(self, s: int) -> bool:
        if s in self.folded or self.stack[s] == 0:
            return False
        if self.bet[s] < self.max_bet:
            return True
        return s not in self.acted and s not in self.sits_out

    def _advance(self) -> None:
        """Set `self.actor`, closing streets (refund, next street, or hand end) while nobody must act."""
        while True:
            if len(self.live) == 1:
                self._close_street()
                self.over, self.actor = True, None
                return
            i = self.order.index(self.last)
            nxt = [self.order[(i + k) % len(self.order)] for k in range(1, len(self.order) + 1)]
            self.actor = next((s for s in nxt if self._needs_action(s)), None)
            if self.actor is not None:
                return
            self._close_street()
            if self.street == 3:
                self.over = True
                return
            self.street += 1
            self._begin_street()

    def _close_street(self) -> None:
        bets = sorted(self.bet.values())
        cutoff = bets[-2] if len(bets) > 1 else 0
        for s in self.order:
            over = self.bet[s] - cutoff
            if over > 0:
                self.stack[s] += over
                self.paid[s] -= over
            self.bet[s] = 0
        self.max_bet = 0

    def apply(self, a: dict) -> None:
        t, w = self.tally, self.where
        s, kind, amount = a["seat"], a["action"], a["amount"]
        if not t.check("action_order", not self.over and s == self.actor,
                       f"{w}: seat {s} acted, expected {'nobody (hand over)' if self.over else self.actor}"):
            raise _Desync
        t.check("street_flow", a["street"] == _BOARD_LEN[self.street],
                f"{w}: action on street board={a['street']}, expected {_BOARD_LEN[self.street]}")
        to_call = min(self.max_bet - self.bet[s], self.stack[s])
        ok = a["facing_bet"] == (to_call > 0)
        if kind == "fold":
            self.folded.add(s)
        elif kind == "call":
            ok &= amount == to_call
            self._put(s, to_call)
        else:
            own_all_in = self.bet[s] + self.stack[s]
            match_all_in = max((self.bet[o] + self.stack[o] for o in self.live if o != s), default=0)
            all_in_to = min(own_all_in, match_all_in)
            may_raise = (self.stack[s] > to_call and match_all_in > self.max_bet
                         and not (0 < self.short_sum < self.full_inc and s in self.closed))
            min_to = self.max_bet + max(self.bb, self.full_inc)
            ok &= may_raise and self.max_bet < amount <= own_all_in and (amount >= min_to or amount >= all_in_to)
            if ok:
                inc = amount - self.max_bet
                if inc >= self.full_inc:
                    self.closed.clear()
                self.full_inc = max(self.full_inc, inc)
                self._put(s, amount - self.bet[s])
                self.max_bet = amount
                self.short_sum = self.short_sum + inc if self.stack[s] == 0 else 0
                if self.short_sum >= self.full_inc:
                    self.short_sum = 0
        t.check("bet_sizing", ok, f"{w}: seat {s} {kind} {amount} (to call {to_call}, max bet {self.max_bet}, "
                                  f"largest raise {self.full_inc}, stack {self.stack[s]})")
        if not ok and kind == "raise":
            raise _Desync
        self.acted.add(s)
        self.closed.add(s)
        self.last = s
        self._advance()


class _Desync(Exception):
    """The engine took an action the model cannot follow; the rest of the hand is not checkable."""


def _level_for_minutes(levels, minutes: int):
    """Level in force after `minutes` of tournament time (the last level repeats). Independent of the director."""
    end = 0
    for lv in levels:
        end += lv.length
        if minutes < end:
            return lv
    return levels[-1]


def check_game(cfg, events: Iterable, result, tally: Tally | None = None, label: str = "") -> Tally:
    """Replay one game's events (as emitted to `run_game`'s observer) and its `GameResult` into `tally`."""
    tally = tally or Tally()
    total = cfg.starting_stack * cfg.players
    stacks = {p: cfg.starting_stack for p in range(cfg.players)}
    buttons: dict[int, int] = {}
    busted_by_round: dict[int, list[tuple[int, int]]] = defaultdict(list)
    round_chips: dict[int, dict[int, int]] = {}
    hand = d = None
    showdown = None
    clock_s, round_no, round_max = 0, None, 0  # virtual clock (length_unit='minutes'): see GATES.md Gate R
    for e in events:
        if e.type == "NEW_HAND":
            d = e.data
            where = f"{label} hand {e.hand_id} (round {d['hand_no']}, table {e.table_id})"
            if d["hand_no"] != round_no:
                clock_s += round_max * cfg.seconds_per_seat
                round_no, round_max = d["hand_no"], 0
            round_max = max(round_max, len(d["seat_players"]))
            lv = (_level_for_minutes(cfg.levels, clock_s // 60) if cfg.length_unit == "minutes"
                  else cfg.level_at(d["hand_no"]))
            tally.check("antes_blinds", (d["sb"], d["bb"], d["ante"]) == (lv.sb, lv.bb, lv.ante),
                        f"{where}: blinds {d['sb']}/{d['bb']}/{d['ante']}, schedule says {lv.sb}/{lv.bb}/{lv.ante}")
            ok = all(stacks.get(p) == d["stacks"][s] and d["stacks"][s] > 0 for s, p in d["seat_players"].items())
            tally.check("stack_continuity", ok, f"{where}: start stacks {d['stacks']} do not continue {stacks}")
            if e.table_id in buttons:
                occ = set(d["seat_players"])
                prev = buttons[e.table_id]
                want = next((prev + k) % cfg.table_size for k in range(1, cfg.table_size + 1)
                            if (prev + k) % cfg.table_size in occ)
                tally.check("button", d["button"] == want, f"{where}: button {d['button']}, expected {want}")
            buttons[e.table_id] = d["button"]
            hand = _HandModel(cfg, d, tally, where)
            tally.check("antes_blinds", tuple(d.get("blind_seats", ())) == (hand.sb_seat, hand.bb_seat),
                        f"{where}: blind seats {d.get('blind_seats')}, rules say SB {hand.sb_seat} BB {hand.bb_seat} "
                        f"(short_stack_rule={cfg.short_stack_rule!r}, stacks {d['stacks']})")
            first_action = True
            showdown = None
        elif e.type == "ACTION" and hand is not None:
            if first_action:
                a = e.data
                to_call = min(hand.max_bet - hand.bet[a["seat"]], hand.stack[a["seat"]]) if a["seat"] == hand.actor else None
                if a["action"] == "call":
                    tally.check("antes_blinds", a["amount"] == to_call,
                                f"{where}: first call {a['amount']}, postings imply {to_call}")
                first_action = False
            try:
                hand.apply(e.data)
            except _Desync:
                hand = None
        elif e.type == "SHOWDOWN":
            showdown = e.data
        elif e.type == "HAND_END":
            fs = e.data["final_stacks"]
            ok = sum(e.data["deltas"].values()) == 0 and all(
                fs[s] - d["stacks"][s] == e.data["deltas"][s] for s in fs)
            tally.check("chip_conservation", ok, f"{where}: deltas {e.data['deltas']} do not conserve chips")
            if hand is not None:
                if not hand.over:
                    tally.check("action_order", False, f"{where}: hand ended but seat {hand.actor} was still to act")
                else:
                    _check_settlement(hand, showdown, fs, tally, where)
            for s, p in d["seat_players"].items():
                stacks[p] = fs[s]
                if fs[s] == 0:
                    del stacks[p]
                    busted_by_round[d["hand_no"]].append((p, d["stacks"][s]))
            hand = None
            round_chips[d["hand_no"]] = dict(stacks)
    for rnd, chips in round_chips.items():  # stacks after the round's last hand
        tally.check("chip_conservation", sum(chips.values()) == total,
                    f"{label} round {rnd}: {sum(chips.values())} chips in play, expected {total}")
    _check_ranks(cfg, result, busted_by_round, stacks, tally, label)
    return tally


def _check_settlement(hand: _HandModel, showdown, final: dict, tally: Tally, where: str) -> None:
    live = hand.live
    if len(live) > 1:
        ok = (showdown is not None and set(showdown["hands"]) == set(live) and len(showdown["board"]) == 5)
        tally.check("street_flow", ok, f"{where}: showdown {showdown and sorted(showdown['hands'])}, "
                                       f"expected seats {sorted(live)} with a 5-card board")
        if not ok:
            return
        keys = {s: strength(showdown["hands"][s], showdown["board"]) for s in live}
    else:
        tally.check("street_flow", showdown is None, f"{where}: showdown with a single live seat")
        keys = {}
    try:
        won = settle(hand.paid, hand.folded, keys, hand.order, hand.antes)
    except ValueError as err:
        tally.check("settlement", False, f"{where}: cannot settle ({err})")
        return
    want = {s: hand.stack[s] + won[s] for s in hand.order}
    tally.check("settlement", want == {s: final[s] for s in hand.order},
                f"{where}: engine final stacks {dict(final)}, independent settlement {want}")


def _check_ranks(cfg, result, busted_by_round, survivors: dict, tally: Tally, label: str) -> None:
    ranks = result.ranks
    ok = sorted(ranks) == list(range(1, cfg.players + 1)) and len(survivors) == 1
    ok &= all(ranks[p] == 1 for p in survivors)
    remaining = cfg.players
    for rnd in sorted(busted_by_round):
        group = busted_by_round[rnd]
        places = sorted(ranks[p] for p, _ in group)
        ok &= places == list(range(remaining - len(group) + 1, remaining + 1))
        by_place = sorted(group, key=lambda b: ranks[b[0]])
        ok &= all(a[1] >= b[1] for a, b in zip(by_place, by_place[1:]))
        remaining -= len(group)
    tally.check("elimination", ok, f"{label}: ranks {ranks} disagree with bust order {dict(busted_by_round)}")
    amounts = cfg.payout_amounts()
    want = [float(amounts[r - 1]) if r <= len(amounts) else 0.0 for r in ranks]
    ok = all(abs(a - b) <= 1e-6 * max(1.0, cfg.prize_pool) for a, b in zip(result.prizes, want))
    ok &= abs(sum(result.prizes) - cfg.prize_pool) <= 1e-6 * max(1.0, cfg.prize_pool)
    tally.check("prizes", ok, f"{label}: prizes {result.prizes} vs payouts by rank {want}")
