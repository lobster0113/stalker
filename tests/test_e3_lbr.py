import numpy as np

from referee.e3 import lbr as L
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR


def folder(key, acts):
    return [1.0 if a == "f" else 0.0 for a in acts] if "f" in acts else None


def test_lbr_crushes_a_policy_that_folds_to_any_bet():
    r = L.lbr(folder, seat=0, hands=30, seed=1)
    # UTG raises every hand and collects the blinds (1.5bb) at least.
    assert r.mean_bb >= 1.4


def test_lbr_is_reproducible_and_reports_every_seat():
    a = L.exploitability_lb({}, 3, seed=2, seats=[0, 5])
    assert a == L.exploitability_lb({}, 3, seed=2, seats=[0, 5])
    assert set(a["by_seat"]) == {"UTG", "BB"}


def test_lbr_reads_the_policy_with_the_training_keys():
    m = E3MCCFR(3, 5)
    m.iterate(2)
    seen = []

    def spy(key, acts):
        seen.append(key)
        return m.policy().get(key)
    L.lbr(spy, seat=2, hands=2, seed=4)
    assert seen and all(k.split("|")[-1].startswith("e") for k in seen)  # TP keys end in the equity step
    assert any(k in m.policy() for k in seen) or not m.policy()


def test_seat_probs_zero_board_collisions():
    s = G.deal(np.random.default_rng(5))
    for a in ("c", "f", "f", "f", "f", "c"):
        s = G.apply(s, a)
    pr = L.seat_probs({}, s, s.to_act, K.initial_ranges(6), 5)
    from stalker.e2.eq_view import COMBO_ARR
    dead = np.isin(COMBO_ARR, list(s.board)).any(axis=1)
    assert np.all(pr[dead] == 0) and np.allclose(pr[~dead].sum(axis=1), 1)


def test_lbr_never_reads_cards_that_are_not_dealt_yet():
    # #257 review: facing an all-in, a call ends the hand and the engine deals the runout; the call's
    # value must come from the dealt board only, so shuffling the undealt deck cannot change it.
    rng = np.random.default_rng(257)
    s = G.deal(rng, 3)
    s = G.apply(s, "a")                       # UTG shoves
    s = G.apply(s, "f")                       # SB folds; the BB faces the all-in alone
    me = s.to_act
    assert "c" in G.legal(s)
    ranges = K.initial_ranges(s.n)
    mine = np.zeros(K.N, dtype=bool)
    values = set()
    for k in range(4):
        deck = list(s.deck)
        np.random.default_rng(k).shuffle(deck)
        values.add(round(L._value({}, s._replace(deck=tuple(deck)), "c", ranges, mine, me, 5, "full"), 9))
    assert len(values) == 1, values


def test_lbr_hands_conserve_chips(monkeypatch):
    # Acceptance criterion: every LBR hand ends with integer results that sum to zero.
    real, ends = G.payoff, []

    def checked(s):
        out = real(s)
        ends.append(out)
        return out

    monkeypatch.setattr(L.G, "payoff", checked)
    L.lbr({}, seat=0, hands=12, seed=4, k=5, n=6, depth="basic")
    assert len(ends) >= 12
    assert all(int(x.sum()) == 0 and np.issubdtype(x.dtype, np.integer) for x in ends)


def test_current_policy_rows_are_distributions_over_the_legal_actions():
    import re

    m = E3MCCFR(2, 5, 6, "basic")
    m.iterate(3)
    cur = m.current_policy()
    assert cur and set(cur) == set(m.regret)
    for key, row in cur.items():
        legal = key.split("|")[-2]
        assert len(row) == len(re.findall(r"b33|b75|[fcrka]", legal)) == len(m.regret[key])
        assert abs(sum(row) - 1) < 1e-9 and min(row) >= 0
    zero = next(iter(m.regret))
    m.regret[zero][:] = 0
    assert np.allclose(m.current_policy()[zero], 1 / len(m.regret[zero]))
