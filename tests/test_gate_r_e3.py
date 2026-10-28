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
