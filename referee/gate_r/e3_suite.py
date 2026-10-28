"""Gate R for the E3 engine (#203): random 6- and 9-handed hands replayed in PokerKit, chip for chip.

`python -m referee.gate_r.e3_suite [--hands N]` (`gates full`, metrics `gate_r_e3_pass_rate`/`_checks`).

E3 (`stalker/e3/game.py`) is the abstract N-handed NLHE game the TP-key policies train on. Each
seeded random hand is replayed in PokerKit, the independent rules engine Gate R already trusts, with
the same hole cards and board:
  e3_actor   after every action both engines agree on who acts next and on the street
  e3_stacks  ... and on every player's remaining stack
  e3_result  at the end each player's net result is the same (fold wins, uncalled chips, splits and
             odd chips)
  e3_chips   E3's own accounting: results sum to zero, nobody puts in more than the stack, the pot is
             the sum of contributions
Seat mapping: E3 numbers seats in preflop order (0 = UTG ... n-2 = SB, n-1 = BB); PokerKit numbers
them from the small blind (heads-up from the big blind).
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
from pokerkit import Automation as A
from pokerkit import NoLimitTexasHoldem

from referee.gate_r.checks import Tally
from stalker.core.cards import card_str
from stalker.e3 import game as G

E3_ITEMS = ("e3_actor", "e3_stacks", "e3_result", "e3_chips")
SEATS = (6, 9)
QUICK_HANDS = 1000  # per table size; the issue's floor
AUTO = (A.ANTE_POSTING, A.BET_COLLECTION, A.BLIND_OR_STRADDLE_POSTING, A.CARD_BURNING,
        A.RUNOUT_COUNT_SELECTION, A.HOLE_CARDS_SHOWING_OR_MUCKING, A.HAND_KILLING, A.CHIPS_PUSHING,
        A.CHIPS_PULLING)


def tally_for_e3() -> Tally:
    return Tally(counts={k: [0, 0] for k in E3_ITEMS})


def pk_index(n: int) -> list[int]:
    """PokerKit player index of each E3 seat."""
    if n == 2:
        return [1, 0]
    return [p + 2 for p in range(n - 2)] + [0, 1]


def _deal_boards(st, board: list[int], dealt: int) -> int:
    while st.can_deal_board():
        k = 3 if dealt == 0 else 1
        st.deal_board("".join(card_str(c) for c in board[dealt:dealt + k]))
        dealt += k
    return dealt


def replay_hand(rng: np.random.Generator, n: int, tally: Tally, where: str) -> None:
    s = G.deal(rng, n)
    board = list(s.deck[:5])
    pk = pk_index(n)
    seat_of = {v: p for p, v in enumerate(pk)}
    st = NoLimitTexasHoldem.create_state(AUTO, True, 0, (G.SB, G.BB), G.BB, (G.STACK,) * n, n)
    for rnd in range(2):
        for i in range(n):
            st.deal_hole(card_str(s.hole[seat_of[i]][rnd]))
    dealt, step = 0, 0
    while not s.done:
        acts = G.legal(s)
        a = acts[int(rng.integers(len(acts)))]
        ns = G.apply(s, a)
        p = s.to_act
        if a == "f":
            st.fold()
        elif a in ("c", "k"):
            st.check_or_call()
        else:  # raise-to = this street's total for p (ns.bet resets when the action closes the street)
            st.complete_bet_or_raise_to(ns.total[p] - (s.total[p] - s.bet[p]))
        s, step = ns, step + 1
        dealt = _deal_boards(st, board, dealt)
        if s.done:
            break
        at = f"{where} step {step} {s.history[-1]}"
        tally.check("e3_actor", st.actor_index == pk[s.to_act] and st.street_index == s.street,
                    f"{at}: E3 seat {s.to_act} street {s.street}, PokerKit actor {st.actor_index} street {st.street_index}")
        tally.check("e3_stacks", all(st.stacks[pk[q]] == s.stack[q] for q in range(n)),
                    f"{at}: E3 {list(s.stack)} PokerKit {[st.stacks[pk[q]] for q in range(n)]}")
    _deal_boards(st, board, dealt)
    pay = G.payoff(s)
    pk_pay = [st.stacks[pk[q]] - G.STACK for q in range(n)]
    tally.check("e3_result", not st.status and list(pay) == pk_pay,
                f"{where} {' '.join(s.history)}: E3 {list(pay)} PokerKit {pk_pay}")
    tally.check("e3_chips", int(pay.sum()) == 0 and max(s.total) <= G.STACK and s.pot == sum(s.total),
                f"{where}: results sum {int(pay.sum())}, max contribution {max(s.total)}")


def run_e3_suite(hands: int = QUICK_HANDS, seats=SEATS, seed: int = 203) -> Tally:
    tally = tally_for_e3()
    for n in seats:
        rng = np.random.default_rng([seed, n])
        for h in range(hands):
            replay_hand(rng, n, tally, f"{n}-max hand {h}")
    return tally


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m referee.gate_r.e3_suite")
    ap.add_argument("--hands", type=int, default=QUICK_HANDS, help="random hands per table size (6, 9)")
    a = ap.parse_args(argv)
    tally = run_e3_suite(a.hands)
    for item, (passed, total) in tally.counts.items():
        print(f"{item:10s} {passed}/{total}")
    print(f"gate_r_e3: {tally.passed}/{tally.total} ({tally.pass_rate:.4%})")
    if tally.passed == tally.total:
        return 0
    print("\n".join("  " + f for f in tally.failures))
    print("fix stalker/e3/game.py (failing test first), or referee/gate_r/e3_suite.py via referee-change if the "
          "seat mapping or replay is wrong")
    return 1


if __name__ == "__main__":
    sys.exit(main())
