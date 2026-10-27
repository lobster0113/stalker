"""Gate R, cash-game skeleton (SIM-c0): rules and invariants checked on a mock event stream.

No engine exists yet (`CashSession` is SIM-b); this fixes the rule table and the five check names so that the
engine is written against them. Rules (v1, see `referee/GATES.md`): fixed blinds, no straddle, no rake, a fixed
set of `seats` seats for the whole session (nobody joins or leaves, so the button visits every seat in order), a
seat with no chips must re-buy before the next hand (a hand never starts with an empty stack), a seat below the cap
may top up between hands (stack + top-up <= `max_buyin`), the session ends after exactly `hands` hands.

Stream (list of dicts, in order):
  SEAT      {seat, amount}                         initial buy-in
  HAND      {button, stacks: {seat: chips}}        stacks after buy-ins/top-ups, before blinds
  HAND_END  {stacks: {seat: chips}}                stacks after settlement
  REBUY     {seat, amount, stack}                  stack = chips before the re-buy
  TOPUP     {seat, amount, stack}                  stack = chips before the top-up
REBUY/TOPUP between a HAND and its HAND_END are in-hand and therefore illegal.

`check_cash_hands` replays the per-hand public events (NEW_HAND/ACTION/SHOWDOWN/HAND_END, as the engine emits
them to its observer) with the tournament model in `checks.py`: same postings, action order, bet sizing and
side-pot settlement, with fixed blinds and no ante.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from referee.gate_r.checks import Tally, _check_settlement, _Desync, _HandModel

CASH_ITEMS = ("cash_rebuy", "cash_topup", "button", "chip_conservation", "session_length")
CASH_HAND_ITEMS = ("antes_blinds", "action_order", "bet_sizing", "street_flow", "settlement")


@dataclass(frozen=True)
class CashRules:
    seats: int
    sb: int
    bb: int
    min_buyin: int
    max_buyin: int
    hands: int
    rake: int = 0  # v1: no rake


def tally_for_cash(items: tuple[str, ...] = CASH_ITEMS) -> Tally:
    return Tally(counts={k: [0, 0] for k in items})


@dataclass(frozen=True)
class _Table:
    """The slice of a tournament config `_HandModel` reads."""
    table_size: int
    ante_mode: str = "none"


def check_cash_hands(rules: CashRules, events: Iterable, tally: Tally, where: str = "cash") -> None:
    """Replay one session's per-hand events; `tally` needs CASH_HAND_ITEMS and `chip_conservation`."""
    table = _Table(rules.seats)
    hand = d = showdown = None
    for e in events:
        if e.type == "NEW_HAND":
            d, showdown = e.data, None
            at = f"{where} hand {e.hand_id}"
            tally.check("antes_blinds", (d["sb"], d["bb"], d["ante"]) == (rules.sb, rules.bb, 0),
                        f"{at}: blinds {d['sb']}/{d['bb']}/{d['ante']}, rules fix {rules.sb}/{rules.bb}/0")
            hand = _HandModel(table, d, tally, at)
        elif e.type == "ACTION" and hand is not None:
            try:
                hand.apply(e.data)
            except _Desync:
                hand = None
        elif e.type == "SHOWDOWN":
            showdown = e.data
        elif e.type == "HAND_END" and d is not None:
            fs = e.data["final_stacks"]
            tally.check("chip_conservation", sum(e.data["deltas"].values()) == 0 and all(
                fs[s] - d["stacks"][s] == e.data["deltas"][s] for s in fs), f"{at}: deltas {e.data['deltas']}")
            if hand is not None:
                if not hand.over:
                    tally.check("action_order", False, f"{at}: hand ended but seat {hand.actor} was still to act")
                else:
                    _check_settlement(hand, showdown, fs, tally, at)
            hand = d = None


def check_cash_session(rules: CashRules, events: list[dict], tally: Tally, where: str = "cash") -> None:
    stack: dict[int, int] = {}
    bought: dict[int, int] = {}
    in_hand, hands, prev_button = False, 0, None
    seated_closed = False  # set by the first HAND: the table is fixed from then on
    hand_start: dict[int, int] = {}

    def buy(seat: int, amount: int) -> None:
        stack[seat] = stack.get(seat, 0) + amount
        bought[seat] = bought.get(seat, 0) + amount

    for i, ev in enumerate(events):
        t, at = ev["type"], f"{where} event {i}"
        if t == "SEAT":
            tally.check("session_length", not seated_closed, f"{at}: seat added after the first hand (seat count is fixed)")
            tally.check("cash_rebuy", rules.min_buyin <= ev["amount"] <= rules.max_buyin,
                        f"{at}: initial buy-in {ev['amount']} outside [{rules.min_buyin}, {rules.max_buyin}]")
            buy(ev["seat"], ev["amount"])
        elif t == "REBUY":
            s = ev["seat"]
            ok = (not in_hand and ev["stack"] == stack.get(s) == 0
                  and rules.min_buyin <= ev["amount"] <= rules.max_buyin)
            tally.check("cash_rebuy", ok, f"{at}: re-buy needs an empty stack between hands within buy-in limits")
            buy(s, ev["amount"])
        elif t == "TOPUP":
            s = ev["seat"]
            ok = (not in_hand and ev["stack"] == stack.get(s) and 0 < ev["stack"]
                  and 0 < ev["amount"] and ev["stack"] + ev["amount"] <= rules.max_buyin)
            tally.check("cash_topup", ok, f"{at}: top-up needs a non-empty stack, between hands, total <= max buy-in")
            buy(s, ev["amount"])
        elif t == "HAND":
            hands += 1
            seated_closed = True
            seats = sorted(ev["stacks"])
            tally.check("session_length", len(seats) == rules.seats,
                        f"{at}: {len(seats)} seats in the hand, rules fix {rules.seats}")
            tally.check("cash_rebuy", min(ev["stacks"].values()) > 0,
                        f"{at}: a hand started with an empty stack (re-buy first)")
            tally.check("chip_conservation", ev["stacks"] == {s: c for s, c in stack.items()},
                        f"{at}: hand stacks differ from tracked stacks")
            nxt = seats[0] if prev_button is None else next((s for s in seats if s > prev_button), seats[0])
            tally.check("button", prev_button is None and ev["button"] in seats or ev["button"] == nxt,
                        f"{at}: button {ev['button']} should be {nxt}")
            prev_button, in_hand, hand_start = ev["button"], True, dict(ev["stacks"])
        elif t == "HAND_END":
            end = ev["stacks"]
            tally.check("chip_conservation",
                        sum(end.values()) == sum(hand_start.values()) and set(end) == set(hand_start)
                        and min(end.values(), default=0) >= 0,
                        f"{at}: table chips changed in a hand ({sum(hand_start.values())} -> {sum(end.values())})")
            stack, in_hand = dict(end), False
    tally.check("session_length", hands == rules.hands and not in_hand,
                f"{where}: {hands} hands played, expected {rules.hands}")
    # per-seat net result is final stack minus everything bought; it must sum to zero (no rake)
    net = sum(stack.get(s, 0) - bought.get(s, 0) for s in bought)
    tally.check("chip_conservation", net == -rules.rake * hands, f"{where}: session net {net} != -rake")
