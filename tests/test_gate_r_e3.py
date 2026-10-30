import numpy as np

from referee.gate_r import e3_suite as E
from stalker.e3 import game as G


def test_seat_mapping_puts_the_blinds_first_in_pokerkit():
    assert E.pk_index(6) == [2, 3, 4, 5, 0, 1]   # UTG HJ CO BTN SB BB -> PokerKit SB=0, BB=1
    assert E.pk_index(2) == [1, 0]               # heads-up: PokerKit 0 is the big blind


def test_random_hands_agree_with_pokerkit():
    t = E.run_e3_suite(hands=60, seats=(2, 6, 9))
    assert t.total > 0 and t.passed == t.total, t.failures


def test_a_wrong_payoff_is_caught(monkeypatch):
    real = G.payoff

    def skewed(s):  # moves one chip from the last seat to the first: PokerKit and conservation disagree
        out = real(s).copy()
        out[0] += 1
        return out

    monkeypatch.setattr(G, "payoff", skewed)
    t = E.tally_for_e3()
    for h in range(5):
        E.replay_hand(np.random.default_rng(h), 6, t, f"h{h}")
    assert t.counts["e3_result"][0] == 0 and t.counts["e3_chips"][0] == 0


def test_edge_cases_agree_with_pokerkit():
    t = E.run_edge_cases()
    assert t.counts["e3_raise"][1] > 0 and t.counts["e3_result"][1] > 0
    assert t.passed == t.total, t.failures


def test_edge_cases_cover_the_412_rules():
    names = {c["name"] for c in E.EDGE_CASES}
    assert {"short all in does not reopen", "min raise after an all in", "non-all-in 5-bet",
            "raise to 80% of the stack", "raise to 99% of the stack"} <= names
    s = E.edge_state(E.EDGE_CASES[0])
    for step in E.EDGE_CASES[0]["line"][:3]:
        s = E.edge_step(s, step)
    assert s.to_act == 0 and G.legal(s) == ["f", "c"]   # the opener faces the short all in


def test_a_reopening_short_all_in_is_caught(monkeypatch):
    # Mutation: every raise reopens the betting, short all ins included (the bug fixed in #412).
    monkeypatch.setattr(G, "_reopens", lambda s, to: True)
    t = E.run_edge_cases()
    assert t.counts["e3_raise"][0] < t.counts["e3_raise"][1]
    assert any("short all in does not reopen" in f and "PokerKit raise False" in f for f in t.failures)
