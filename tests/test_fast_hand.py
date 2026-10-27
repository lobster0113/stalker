import os

import numpy as np
import pytest

from stalker.tools import bench_engine, diff_engine
from stalker.tournament.fast_hand import FastHand
from stalker.tournament.hand import Hand


def _pair(seed=0, **kw):
    return Hand(rng=np.random.default_rng(seed), **kw), FastHand(rng=np.random.default_rng(seed), **kw)


def test_differential_quick():
    out = diff_engine.run(600, seed=20261024)
    assert out["mismatches"] == 0, out["failures"]


@pytest.mark.slow
def test_differential_100k_hands():
    # Acceptance for #19: 100k random hands with identical legal-action sets and HandResults.
    out = diff_engine.run(100_000, seed=1, workers=max(1, os.cpu_count() or 1))
    assert out["mismatches"] == 0, out["failures"]


@pytest.mark.slow
def test_throughput_at_least_20x_pokerkit():
    out = bench_engine.main(["--players", "9", "--seconds", "2"])
    assert out["speedup"] >= 20, out


def test_heads_up_button_posts_small_blind_and_acts_first():
    _, fast = _pair(stacks=[100, 100], button=1, small_blind=1, big_blind=2)
    la = fast.legal_actions()
    assert la.seat == 1 and la.call_amount == 1 and la.min_raise_to == 4 and la.max_raise_to == 100


def test_short_all_in_does_not_reopen_betting():
    kw = dict(stacks=[1000, 1000, 1000, 130], button=0, small_blind=5, big_blind=10)
    ref, fast = _pair(**kw)
    for h in (ref, fast):
        h.check_or_call()   # seat 3 (UTG) limps 10
        h.raise_to(100)     # seat 0 (button) raises to 100
        h.check_or_call()   # seat 1 (SB) calls
        h.check_or_call()   # seat 2 (BB) calls
    # Seat 3 shoves 130: a 30 raise, short of the 90 full raise, so earlier actors may only call or fold.
    for h in (ref, fast):
        h.raise_to(130)
    la = fast.legal_actions()
    assert la == ref.legal_actions()
    assert la.seat == 0 and la.call_amount == 30 and la.min_raise_to is None


def test_odd_chip_goes_to_first_winner_left_of_button():
    # Seed 36 deals a board-playing split; the BB ante makes the 5-chip pot odd.
    kw = dict(stacks=[50, 50], button=0, small_blind=1, big_blind=2, ante=1, ante_mode="bb_ante")
    ref, fast = _pair(36, **kw)
    for h in (ref, fast):
        while not h.is_over:
            h.check_or_call()
    assert fast.result() == ref.result()
    (award,) = fast.result().awards
    assert award.amount == 5 and award.awards == {1: 3, 0: 2}  # seat 1 (BB, left of button) gets the odd chip


def test_uncalled_bet_is_returned():
    _, fast = _pair(stacks=[100, 40], button=0, small_blind=1, big_blind=2)
    fast.raise_to(100)  # button shoves 100 into a 40 stack
    fast.check_or_call()
    res = fast.result()
    assert sum(p.amount for p in res.pots) == 80
    assert sum(res.final_stacks) == 140


def test_illegal_actions_raise():
    _, fast = _pair(stacks=[100, 100, 100], button=0, small_blind=1, big_blind=2)
    with pytest.raises(ValueError, match="raise_to"):
        fast.raise_to(3)  # min raise-to is 4
    fast.check_or_call()
    fast.check_or_call()
    with pytest.raises(ValueError, match="fold"):
        fast.fold()  # BB can check
    fast.check_or_call()
    with pytest.raises(RuntimeError):
        fast.result()


def test_same_seed_same_actions_replay():
    rng = np.random.default_rng(3)
    for _ in range(100):
        spec = diff_engine.random_spec(rng)
        seed = int(rng.integers(2**63))
        hand = FastHand(rng=np.random.default_rng(seed), **spec)
        bench_engine.play_random(hand, rng)
        replay = FastHand(rng=np.random.default_rng(seed), **spec)
        for seat, kind, amount in hand.actions():
            assert replay.actor == seat
            {"f": replay.fold, "cc": replay.check_or_call, "cbr": lambda: replay.raise_to(amount)}[kind]()
        assert replay.is_over and replay.result() == hand.result() and replay.board() == hand.board()


def test_validation_matches_hand():
    for bad in (dict(stacks=[100, 0], button=0), dict(stacks=[100, 100], button=1, ante=1),
                dict(stacks=[100, -1, 5], button=0)):
        kw = dict(small_blind=1, big_blind=2) | bad
        with pytest.raises(ValueError):
            FastHand(rng=np.random.default_rng(0), **kw)


def test_public_state_accessors_match_pokerkit():
    # stacks/bets/pot feed agent observations in CashSession, so both engines must report them identically.
    rng = np.random.default_rng(99)
    for seed in range(40):
        n = int(rng.integers(2, 10))
        kw = dict(stacks=[int(x) for x in rng.integers(1, 300, n)], button=int(rng.integers(n)),
                  small_blind=1, big_blind=2)
        ref, fast = _pair(seed, **kw)
        while not fast.is_over:
            assert (fast.stacks, fast.bets, fast.pot) == (ref.stacks, ref.bets, ref.pot)
            la = fast.legal_actions()
            r = rng.random()
            for h in (ref, fast):
                if la.can_fold and r < 0.2:
                    h.fold()
                elif la.min_raise_to is not None and r > 0.7:
                    h.raise_to(la.min_raise_to if r < 0.9 else la.max_raise_to)
                else:
                    h.check_or_call()
        assert ref.is_over
