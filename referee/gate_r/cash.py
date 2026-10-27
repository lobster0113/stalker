"""Gate R, cash-game skeleton (SIM-c0): rules and invariants checked on a mock event stream.

No engine exists yet (`CashSession` is SIM-b); this fixes the rule table and the five check names so that the
engine is written against them. Rules (v1, see `referee/GATES.md`): fixed blinds, no straddle, no rake, fixed
seat count, a seat that is out of chips may re-buy between hands, a seat below the cap may top up between hands
(stack + top-up <= `max_buyin`), the session ends after exactly `hands` hands, the button moves one occupied seat
clockwise per hand.

Stream (list of dicts, in order):
  SEAT      {seat, amount}                         initial buy-in
  HAND      {button, stacks: {seat: chips}}        stacks after buy-ins/top-ups, before blinds
  HAND_END  {stacks: {seat: chips}}                stacks after settlement
  REBUY     {seat, amount, stack}                  stack = chips before the re-buy
  TOPUP     {seat, amount, stack}                  stack = chips before the top-up
REBUY/TOPUP between a HAND and its HAND_END are in-hand and therefore illegal.
"""
from __future__ import annotations

from dataclasses import dataclass

from referee.gate_r.checks import Tally

CASH_ITEMS = ("cash_rebuy", "cash_topup", "button", "chip_conservation", "session_length")


@dataclass(frozen=True)
class CashRules:
    seats: int
    sb: int
    bb: int
    min_buyin: int
    max_buyin: int
    hands: int
    rake: int = 0  # v1: no rake


def tally_for_cash() -> Tally:
    return Tally(counts={k: [0, 0] for k in CASH_ITEMS})


def check_cash_session(rules: CashRules, events: list[dict], tally: Tally, where: str = "cash") -> None:
    stack: dict[int, int] = {}
    bought: dict[int, int] = {}
    in_hand, hands, prev_button = False, 0, None
    hand_start: dict[int, int] = {}

    def buy(seat: int, amount: int) -> None:
        stack[seat] = stack.get(seat, 0) + amount
        bought[seat] = bought.get(seat, 0) + amount

    for i, ev in enumerate(events):
        t, at = ev["type"], f"{where} event {i}"
        if t == "SEAT":
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
            seats = sorted(ev["stacks"])
            tally.check("chip_conservation", ev["stacks"] == {s: c for s, c in stack.items()},
                        f"{at}: hand stacks differ from tracked stacks")
            nxt = seats[0] if prev_button is None else next((s for s in seats if s > prev_button), seats[0])
            tally.check("button", prev_button is None and ev["button"] in seats or ev["button"] == nxt,
                        f"{at}: button {ev['button']} should be {nxt}")
            prev_button, in_hand, hand_start = ev["button"], True, dict(ev["stacks"])
        elif t == "HAND_END":
            end = ev["stacks"]
            tally.check("chip_conservation", sum(end.values()) == sum(hand_start.values()) and set(end) == set(hand_start),
                        f"{at}: table chips changed in a hand ({sum(hand_start.values())} -> {sum(end.values())})")
            stack, in_hand = dict(end), False
    tally.check("session_length", hands == rules.hands and not in_hand,
                f"{where}: {hands} hands played, expected {rules.hands}")
    # per-seat net result is final stack minus everything bought; it must sum to zero (no rake)
    net = sum(stack.get(s, 0) - bought.get(s, 0) for s in bought)
    tally.check("chip_conservation", net == -rules.rake * hands, f"{where}: session net {net} != -rake")
