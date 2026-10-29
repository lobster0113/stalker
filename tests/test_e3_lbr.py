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


# --- #343: off-menu sizes for the exploiter ---------------------------------------------------------

def uniform(key, acts):
    return [1.0 / len(acts)] * len(acts)


def _flop(n=3, seed=7):
    s = G.deal(np.random.default_rng(seed), n)
    while s.street == 0:
        s = G.apply(s, "c")
    return s


def test_default_lbr_is_bit_identical_to_before_extra_sizes():
    # Golden values taken from main before #343 (uniform policy, k=3, 3 players, 30 hands, seed 3).
    r1, r2 = L.lbr(uniform, 1, 30, seed=3, k=3, n=3), L.lbr(uniform, 2, 30, seed=3, k=3, n=3)
    assert (r1.mean_bb, r1.stderr_bb) == (-3.6, 5.85659074653623)
    assert (r2.mean_bb, r2.stderr_bb) == (6.116666666666666, 10.67725812164193)
    assert L.lbr(uniform, 1, 30, seed=3, k=3, n=3, extra_sizes=False) == r1


def test_translate_size_boundaries():
    s = _flop()
    p, pot = s.to_act, s.pot
    for menu, frac in (("b33", 0.33), ("b75", 0.75)):                 # exactly a menu size
        assert L.translate_size(s, s.bet[p] + int(round(pot * frac))) == menu
    mid = s.bet[p] + int(round(pot * 0.54))                           # half way between 33% and 75%
    assert L.translate_size(s, mid - 5) == "b33" and L.translate_size(s, mid + 5) == "b75"
    assert L.translate_size(s, s.bet[p] + int(pot * 1.5)) == "b75"    # an overbet is nearest the biggest bet
    room = s.stack[p] + s.bet[p]
    assert L.translate_size(s, room) == "a" and L.translate_size(s, room + 500) == "a"   # at or past all in
    facing = G.apply(s, "b75")
    assert L.translate_size(facing, max(facing.bet) + facing.last_raise) == "r"


def test_extra_actions_are_legal_and_conserve_chips():
    checked = 0
    for seed in range(12):
        rng = np.random.default_rng(seed)
        s = G.deal(rng, 4 if seed % 2 else 3)
        while not s.done:
            for x in L.extra_actions(s):
                ns = G.apply_to(s, x.to, x.menu)
                p = s.to_act
                assert x.to >= max(s.bet) + s.last_raise and x.to < s.stack[p] + s.bet[p] - G.BB   # min raise, below all in
                assert ns.stack[p] >= 0 and ns.bet[p] == x.to and ns.history[-1] == f"{p}:{x.menu}"
                assert sum(ns.stack) + ns.pot == sum(s.stack) + s.pot                             # chips conserved
                assert set(G.legal(ns)) <= {"f", "c", "r", "a"}                                   # the next seat has a legal menu
                checked += 1
            acts = G.legal(s)
            s = G.apply(s, acts[int(rng.integers(len(acts)))])
        assert int(G.payoff(s).sum()) == 0
    assert checked > 10


def test_extra_actions_offer_overbets_unopened_and_a_min_raise_facing_a_bet():
    s = _flop()
    assert [x.to - s.bet[s.to_act] for x in L.extra_actions(s)] == [int(round(s.pot * f)) for f in L.OVERBETS]
    f = G.apply(s, "b33")
    xs = L.extra_actions(f)
    assert xs == [L.Extra(max(f.bet) + f.last_raise, "r")] and xs[0].to < G._amount_to(f, "r")
    assert L.extra_actions(G.deal(np.random.default_rng(1))) == []        # preflop: none


def test_apply_to_rejects_illegal_sizes():
    s = _flop()
    p = s.to_act
    for to in (s.bet[p], s.bet[p] + G.BB - 1, s.stack[p] + s.bet[p] + 1):
        try:
            G.apply_to(s, to, "b75")
        except ValueError:
            continue
        raise AssertionError(f"accepted {to}")


def test_extra_sizes_lbr_is_not_below_the_menu_lbr():
    # The exploiter has strictly more actions; same deals and policy. Tolerance: 3 standard errors.
    base = L.exploitability_lb(uniform, 30, seed=3, k=3, n=3)
    ext = L.exploitability_lb(uniform, 30, seed=3, k=3, n=3, extra_sizes=True)
    assert ext["lbr_bb"] >= base["lbr_bb"] - 3 * max(base["stderr_bb"], ext["stderr_bb"])
    assert ext == L.exploitability_lb(uniform, 30, seed=3, k=3, n=3, extra_sizes=True)   # reproducible
