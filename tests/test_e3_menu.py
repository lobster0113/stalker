"""E3 tp6 size menu and raise_cap=None (#339): legal actions per spot, rule invariants, Gate R replay."""
import hashlib
import json

import numpy as np
import pytest

from referee.gate_r.e3_suite import run_e3_suite
from stalker import train_jobs as T
from stalker.e3 import game as G
from stalker.e3 import parallel
from stalker.e3.mccfr import E3MCCFR

RULES = [("v1", 3), ("v1", None), ("tp6", 3), ("tp6", None)]


def play(s: G.State, *acts: str) -> G.State:
    for a in acts:
        assert a in G.legal(s), (a, G.legal(s), s.history)
        s = G.apply(s, a)
    return s


def sizes(s: G.State) -> dict[str, int]:
    return {a: G._amount_to(s, a) for a in G.legal(s) if a not in ("f", "c", "k")}


def tp6(n: int, cap=3) -> G.State:
    return G.deal(np.random.default_rng(0), n, "tp6", cap)


def test_v1_default_is_unchanged():
    # Hash of 900 seeded random v1 hands, computed on main before #339 (same histories, same results).
    h = hashlib.sha256()
    for n in (2, 6, 9):
        rng = np.random.default_rng([339, n])
        for _ in range(300):
            s = G.random_playout(rng, n)
            h.update((" ".join(s.history) + repr(list(G.payoff(s)))).encode())
    assert h.hexdigest() == "9f70921d4d657735f2c698f2d563c9437f622bfac826a5b1d9b038eae1455d97"
    s = G.deal(np.random.default_rng(0), 6)
    assert (s.menu, s.raise_cap) == ("v1", 3)


def test_tp6_preflop_open_sizes():
    s = tp6(6)
    assert G.legal(s) == ["f", "c", "r22", "r", "r3", "a"]
    assert sizes(s) == {"r22": 220, "r": 250, "r3": 300, "a": G.STACK}


def test_tp6_isolation_is_2_5bb_plus_1bb_per_limper():
    s = play(tp6(6), "c")                      # UTG limps
    assert G.legal(s) == ["f", "c", "r", "a"] and sizes(s)["r"] == 350
    s = play(s, "c")                           # HJ limps too
    assert sizes(s)["r"] == 450
    hu = play(tp6(2), "c")                     # heads-up: the SB completing is a limp; the BB may check or isolate
    assert G.legal(hu) == ["c", "r", "a"] and sizes(hu)["r"] == 350


def test_tp6_raise_facing_a_bet_is_2_5_3_4x():
    s = play(tp6(6), "r")                      # UTG opens to 2.5BB
    assert G.legal(s) == ["f", "c", "r25", "r", "r4", "a"]
    assert sizes(s) == {"r25": 625, "r": 750, "r4": 1000, "a": G.STACK}
    # Postflop: limped heads-up pot 200, the BB bets 1BB, the SB faces 100.
    s = play(tp6(2), "c", "c", "b33")
    assert sizes(s) == {"r25": 250, "r": 300, "r4": 400, "a": G.STACK - 100}


def test_tp6_postflop_bets_and_same_amount_offered_once():
    # Pot 200: 33% and 50% both round up to the 1BB minimum bet, so b50 is not offered separately.
    s = play(tp6(2), "c", "c")
    assert G.legal(s) == ["k", "b33", "b75", "b100", "b150", "a"]
    assert sizes(s) == {"b33": 100, "b75": 150, "b100": 200, "b150": 300, "a": G.STACK - 100}
    # Pot 600 (SB opens to 3BB, BB calls): all five sizes are distinct.
    s = play(tp6(2), "r3", "c")
    assert G.legal(s) == ["k", "b33", "b50", "b75", "b100", "b150", "a"]
    assert sizes(s) == {"b33": 198, "b50": 300, "b75": 450, "b100": 600, "b150": 900, "a": G.STACK - 300}


def test_raise_cap_and_no_cap():
    # Heads-up preflop: SB 3BB, BB 4x = 12BB, SB 2.5x = 30BB. Raises after the BB: 3 = the cap.
    capped = play(tp6(2), "r3", "r4", "r25")
    assert G.legal(capped) == ["f", "c", "a"]
    # No cap: room 10,000; 2.5x = 7,500 is offered, 3x = 9,000 >= ALLIN_MERGE x 10,000 merges into the
    # all-in, 4x = 12,000 is more than the stack.
    free = play(tp6(2, None), "r3", "r4", "r25")
    assert G.legal(free) == ["f", "c", "r25", "a"] and sizes(free)["r25"] == 7500
    assert G.ALLIN_MERGE * G.STACK == 8000


@pytest.mark.parametrize("menu,cap", RULES)
def test_rule_invariants_on_random_hands(menu, cap):
    # Every raise reaches the minimum raise or is all in, nobody bets more than the stack, chips are kept.
    for n in (2, 6, 9):
        rng = np.random.default_rng([339, n])
        for _ in range(150):
            s = G.deal(rng, n, menu, cap)
            while not s.done:
                acts = G.legal(s)
                assert len(acts) == len(set(acts))
                p, a = s.to_act, acts[int(rng.integers(len(acts)))]
                if a not in ("f", "c", "k"):
                    to, room = G._amount_to(s, a), s.stack[p] + s.bet[p]
                    assert to <= room
                    assert to == room or to >= max(s.bet) + s.last_raise, (a, to, s.history)
                    if cap is None and a != "a":
                        assert to < G.ALLIN_MERGE * room
                s = G.apply(s, a)
                assert all(s.stack[i] + s.total[i] == G.STACK and s.stack[i] >= 0 for i in range(n))
            assert int(G.payoff(s).sum()) == 0


@pytest.mark.parametrize("menu,cap", [("tp6", 3), ("tp6", None)])
def test_gate_r_pokerkit_replay_on_new_rules(menu, cap):
    # The Gate R E3 replay (PokerKit, chip for chip; it rejects a raise below the minimum) dealt under the
    # new rules. referee/gate_r/e3_suite.py deals with G.deal(rng, n), so G.rules switches it.
    with G.rules(menu, cap):
        t = run_e3_suite(200, seats=(2, 6, 9), seed=339)
    assert t.passed == t.total, t.failures[:3]
    with G.rules(menu, cap):
        assert G.deal(np.random.default_rng(0), 6).menu == menu


def test_rules_context_restores_and_explicit_arguments_win():
    with G.rules("tp6", None):
        s = G.deal(np.random.default_rng(0), 6)
        assert (s.menu, s.raise_cap) == ("tp6", None)
        assert G.deal(np.random.default_rng(0), 6, "v1", 3).menu == "v1"
    s = G.deal(np.random.default_rng(0), 6)
    assert (s.menu, s.raise_cap) == ("v1", 3)
    with pytest.raises(ValueError, match="known menus"):
        G.deal(np.random.default_rng(0), 6, "v2")
    with pytest.raises(ValueError, match="known menus"), G.rules("v2"):
        pass


def test_training_keeps_its_rules_across_workers_and_checkpoints():
    m = E3MCCFR(1, 3, 3, "full", "tp6", None)
    parallel.iterate(m, 4, workers=2, batch=1)
    assert any("b150" in k or "r22" in k for k in m.regret), "tp6 actions should appear in the keys"
    back = E3MCCFR.from_state(json.loads(json.dumps(m.state())))
    assert (back.menu, back.raise_cap) == ("tp6", None) and back.state() == m.state()
    old = m.state()
    del old["menu"], old["raise_cap"]          # a checkpoint written before #339
    assert (E3MCCFR.from_state(old).menu, E3MCCFR.from_state(old).raise_cap) == ("v1", 3)


def test_tp6_jobs_are_registered_and_resumable():
    for job, cap in (("e3-tp-mid-tp6-w4", 3), ("e3-tp-mid-tp6nc-w4", None)):
        kw = T.JOBS[job].keywords
        assert (kw["tier"], kw["workers"], kw["menu"], kw.get("raise_cap", 3)) == ("mid", 4, "tp6", cap)
        assert job in T.RESUMABLE
