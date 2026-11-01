"""Gate R for the E3 engine (#203): random 6- and 9-handed hands replayed in PokerKit, chip for chip.

`python -m referee.gate_r.e3_suite [--hands N]` (`gates full`, metrics `gate_r_e3_pass_rate`/`_checks`).

E3 (`stalker/e3/game.py`) is the abstract N-handed NLHE game the TP-key policies train on. Each
seeded random hand is replayed in PokerKit, the independent rules engine Gate R already trusts, with
the same hole cards and board:
  e3_actor   after every action both engines agree on who acts next and on the street
  e3_stacks  ... and on every player's remaining stack
  e3_result  at the end each player's net result is the same (fold wins, uncalled chips, splits and
             odd chips)
  e3_raise   at every decision E3 offers a raise exactly when PokerKit allows one, with the same
             minimum raise-to
  e3_chips   E3's own accounting: results sum to zero, nobody puts in more than the stack, the pot is
             the sum of contributions
Random hands start from equal stacks (an all in can never be re-raised), and a second batch from
seat-specific 20-250BB stacks (`G.sample_stacks`, #396), which makes short all ins, re-raises over them
and side pots. EDGE_CASES are fixed lines
on stacks set with `State._replace` (#412) for the betting rules equal stacks never reach: a short all in
that does not reopen the betting, a minimum raise after an all in, a non-all-in 5-bet and raises to
80-99% of the stack entered as real sizes (`apply_to`; the training menu does not offer them). `e3_result`
covers side pots (PokerKit settles them) and is checked on every line.
Seat mapping: E3 numbers seats in preflop order (0 = UTG ... n-2 = SB, n-1 = BB); PokerKit numbers
them from the small blind (heads-up from the big blind).
"""
from __future__ import annotations

import argparse
import sys
import warnings

import numpy as np
from pokerkit import Automation as A
from pokerkit import NoLimitTexasHoldem

from referee.gate_r.checks import Tally
from stalker.core.cards import card_str
from stalker.e3 import game as G
from stalker.e3 import translate as T

E3_ITEMS = ("e3_actor", "e3_stacks", "e3_raise", "e3_result", "e3_chips")
SEATS = (2, 3, 4, 5, 6, 9)
QUICK_HANDS = 1000  # per table size; the issue's floor
SHORT_TABLE_DIVISOR = 4  # 2-5 handed tables (#492) replay hands//4: gate_r_e3 grows ~15s, not ~36s
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


def replay_hand(rng: np.random.Generator, n: int, tally: Tally, where: str, unequal: bool = False) -> None:
    s = G.deal(rng, n, stacks=G.sample_stacks(rng, n, equal_p=0.0) if unequal else None)
    _quiet(_replay, s, lambda s: G.apply(s, _pick(rng, G.legal(s))), tally, where)


def _pick(rng: np.random.Generator, acts: list[str]) -> str:
    return acts[int(rng.integers(len(acts)))]


def _quiet(f, *args) -> None:
    # PokerKit warns on every card we choose ourselves; replaying fixed cards is the point (success is quiet).
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="A card being dealt", category=UserWarning)
        f(*args)


def least_raise_to(s: G.State) -> int:
    """E3's minimum raise-to for the seat to act: the current bet plus the last full raise, or all in."""
    p = s.to_act
    return min(max(s.bet) + s.last_raise, s.stack[p] + s.bet[p])


def _replay(s: G.State, step_fn, tally: Tally, where: str) -> None:
    n = s.n
    board = list(s.deck[:5])
    pk = pk_index(n)
    seat_of = {v: p for p, v in enumerate(pk)}
    start = [s.stack[q] + s.bet[q] for q in range(n)]
    st = NoLimitTexasHoldem.create_state(AUTO, True, 0, (G.SB, G.BB), G.BB,
                                         tuple(start[seat_of[i]] for i in range(n)), n)
    for rnd in range(2):
        for i in range(n):
            st.deal_hole(card_str(s.hole[seat_of[i]][rnd]))
    dealt, step = 0, 0
    while not s.done:
        pk_raise, e3_raise = st.can_complete_bet_or_raise_to(), "a" in G.legal(s)
        pk_min = st.min_completion_betting_or_raising_to_amount if pk_raise else None
        e3_min = least_raise_to(s) if e3_raise else None
        tally.check("e3_raise", e3_raise == pk_raise and e3_min == pk_min,
                    f"{where} step {step} after {' '.join(s.history[-3:])}: E3 seat {s.to_act} raise {e3_raise} "
                    f"(min {e3_min}), PokerKit raise {pk_raise} (min {pk_min})")
        ns = step_fn(s)
        p = s.to_act
        if ns.history[len(s.history)] == f"{p}:f":
            st.fold()
        elif ns.total[p] - s.total[p] <= s.to_call():   # chips, not labels: an off-menu size keeps a menu label
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
    pk_pay = [st.stacks[pk[q]] - start[q] for q in range(n)]
    live = s.live()
    tally.check("e3_result", not st.status and list(pay) == pk_pay,
                f"{where} {' '.join(s.history)}: stacks {start}: E3 {list(pay)} PokerKit {pk_pay}")
    tally.check("e3_chips", int(pay.sum()) == 0 and all(s.total[q] <= start[q] for q in range(n))
                and s.pot == sum(s.total),
                f"{where}: results sum {int(pay.sum())}, contributions {list(s.total)}, stacks {start}")


# Fixed lines (#412), three-handed ("n": 4 where given, then 0 = UTG): seat 0 = BTN, 1 = SB, 2 = BB. "short" sets a seat's starting stack
# (before the blinds). A step is a menu label, ("to", chips) a real size, ("min",) the minimum raise, or
# ("room", x) a raise to x of the actor's stack plus street bet. Real sizes go in with G.apply_to, labelled
# with their likeliest reading in stalker/e3/translate.py. After the line the hand is checked or called down.
EDGE_CASES = (
    # 300 open, SB all in for 450 (+150 < the 200 raise): the opener may only call or fold.
    {"name": "short all in does not reopen", "short": {1: 450}, "line": [("to", 300), "a", "c", "c"]},
    # The big blind has not acted yet, so it may raise over the short all in, by the last full raise.
    {"name": "min raise after a short all in", "short": {1: 450}, "line": [("to", 300), "a", ("min",), "c"]},
    # Two short all ins (+150, +110) add up to a full raise (200): the opener may raise again (TDA).
    {"name": "short all ins add up to a full raise", "n": 4, "raise_cap": None, "short": {1: 450, 2: 560},
     "line": [("to", 300), "a", "a", "c", ("min",), "c"]},
    # SB all in for 700 over a 250 open (+450, a full raise): the next minimum raise is to 1150.
    {"name": "min raise after an all in", "short": {1: 700}, "line": [("to", 250), "a", ("min",), "f"]},
    # The real menu's 5-bet is all in only; a person may still 5-bet to 5000 (read as "a").
    {"name": "non-all-in 5-bet", "menu": "real", "line": ["r", "r", "r", ("to", 5000), "f", "c"]},
    # raise_cap=None merges raises to >= 80% of the stack into the all in; a person may still make them.
    {"name": "raise to 80% of the stack", "menu": "real", "raise_cap": None,
     "line": ["r", "f", "c", "b33", ("room", 0.8), "c"]},
    {"name": "raise to 99% of the stack", "menu": "real", "raise_cap": None,
     "line": ["r", "f", "c", "b33", ("room", 0.99), "a", "c"]},
)


def edge_state(case: dict, seed: int = 412) -> G.State:
    s = G.deal(np.random.default_rng(seed), case.get("n", 3), case.get("menu", "v1"),
               case.get("raise_cap", G.RAISE_CAP))
    stack = list(s.stack)
    for q, chips in case.get("short", {}).items():
        stack[q] = chips - s.bet[q]
    return s._replace(stack=tuple(stack))


def edge_step(s: G.State, step) -> G.State:
    if isinstance(step, str):
        return G.apply(s, step)
    room = s.stack[s.to_act] + s.bet[s.to_act]
    to = {"to": lambda: step[1], "min": lambda: least_raise_to(s), "room": lambda: int(step[1] * room)}[step[0]]()
    label = max(T.split(s, to), key=lambda m: m[1])[0]
    return G.apply_to(s, to, label)


def run_edge_cases(tally: Tally | None = None, cases=EDGE_CASES, seed: int = 412) -> Tally:
    tally = tally_for_e3() if tally is None else tally
    for case in cases:
        line = list(case["line"])

        def step_fn(s, line=line):
            if line:
                return edge_step(s, line.pop(0))
            return G.apply(s, "k" if "k" in G.legal(s) else "c")

        _quiet(_replay, edge_state(case, seed), step_fn, tally, f"edge '{case['name']}'")
    return tally


def run_e3_suite(hands: int = QUICK_HANDS, seats=SEATS, seed: int = 203) -> Tally:
    tally = tally_for_e3()
    for n in seats:
        hands_n = hands if n >= 6 else max(1, hands // SHORT_TABLE_DIVISOR)
        rng = np.random.default_rng([seed, n])
        for h in range(hands_n):
            replay_hand(rng, n, tally, f"{n}-max hand {h}")
        rng = np.random.default_rng([seed, n, 396])   # seat-specific 20-250BB stacks: side pots (#396)
        for h in range(hands_n):
            replay_hand(rng, n, tally, f"{n}-max unequal-stack hand {h}", unequal=True)
    return run_edge_cases(tally)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m referee.gate_r.e3_suite")
    ap.add_argument("--hands", type=int, default=QUICK_HANDS, help="random hands per table size (6, 9; 2-5 handed use a quarter)")
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
