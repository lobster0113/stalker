import time

import numpy as np
import pytest

from stalker.core.cards import cards
from stalker.core.icm import icm_equity
from stalker.e3 import game
from stalker.e3.icm_payoff import tournament_payoff

BOARD = cards("KdQs9c4h3s")
WIN, LOSE = cards("AsAh"), cards("2c7d")


def _allin_hand(stacks, shover, callers, winner):
    """Hand where `shover` goes all in, `callers` call and the rest fold; `winner` holds aces."""
    s = game.deal(np.random.default_rng(0), n=len(stacks), stacks=tuple(stacks))
    used = set(BOARD) | set(WIN) | set(LOSE)
    spare = [c for c in range(52) if c not in used]
    hole = []
    for i in range(s.n):
        if i == winner:
            hole.append(tuple(WIN))
        elif not hole or LOSE[0] not in [c for h in hole for c in h]:
            hole.append(tuple(LOSE))
        else:
            hole.append((spare.pop(0), spare.pop(0)))
    s = s._replace(hole=tuple(hole), deck=tuple(BOARD) + tuple(spare))
    while not s.done:
        p = s.to_act
        if p == shover:
            a = "a" if "a" in game.legal(s) else "c"
        elif p in callers:
            a = "c" if "c" in game.legal(s) else "a"
        else:
            a = "f"
        s = game.apply(s, a)
    return s


def test_winner_take_all_is_chip_share_times_pool():
    stacks = [3000, 2000, 1000]
    s = _allin_hand(stacks, shover=0, callers={2}, winner=2)
    chips = game.payoff(s)
    assert chips[2] > 0
    for lam in (0.0, 0.5):   # 3 live, 1 paid place: not the bubble, lam has no effect
        r = tournament_payoff(s, stacks, [100.0], lam=lam)
        assert r == pytest.approx(chips / sum(stacks) * 100.0, abs=1e-9)


def test_heads_up_two_payouts_matches_closed_form():
    stacks = [4000, 6000]
    total = sum(stacks)
    fold = game.apply(game.deal(np.random.default_rng(1), n=2, stacks=tuple(stacks)), "f")
    r = tournament_payoff(fold, stacks, [70.0, 30.0])
    assert r == pytest.approx(40.0 * game.payoff(fold) / total, abs=1e-9)
    bust = _allin_hand(stacks, shover=1, callers={0}, winner=1)   # seat 0 busts and finishes 2nd
    r = tournament_payoff(bust, stacks, [70.0, 30.0])
    before = [30.0 + 40.0 * x / total for x in stacks]
    assert r == pytest.approx([30.0 - before[0], 70.0 - before[1]], abs=1e-9)


def test_bubble_short_stack_call_worth_less_than_chip_ev():
    stacks, payouts = [6000, 6000, 6000, 1000], [50.0, 30.0, 20.0]   # 4 live, 3 paid: the bubble
    win = _allin_hand(stacks, shover=0, callers={3}, winner=3)
    lose = _allin_hand(stacks, shover=0, callers={3}, winner=0)
    pool_per_chip = sum(payouts) / sum(stacks)
    chip_ev = 0.5 * (game.payoff(win)[3] + game.payoff(lose)[3]) * pool_per_chip
    icm_ev = 0.5 * (tournament_payoff(win, stacks, payouts)[3] + tournament_payoff(lose, stacks, payouts)[3])
    assert chip_ev > 0 > icm_ev   # a +chip-EV coin flip for the short stack loses prize equity


def _random_hands(seed, count):
    rng = np.random.default_rng(seed)
    for _ in range(count):
        n = int(rng.integers(2, 10))
        stacks = [int(x) * game.BB for x in rng.integers(2, 60, size=n)]
        yield game.random_playout(rng, n=n, stacks=tuple(stacks)), stacks


def test_lambda_zero_equals_icm_difference_for_surviving_players():
    payouts = [50.0, 30.0, 20.0]
    for s, stacks in _random_hands(879, 60):
        after = np.array(stacks) + game.payoff(s)
        r = tournament_payoff(s, stacks, payouts, lam=0.0)
        icm = np.array(icm_equity(after, payouts)) - np.array(icm_equity(stacks, payouts))
        alive = after > 0
        assert r[alive] == pytest.approx(icm[alive], abs=1e-9)


def test_prize_pool_conserved_including_busts():
    busts = 0
    for s, stacks in _random_hands(880, 80):
        busts += int(np.any(np.array(stacks) + game.payoff(s) == 0))
        for lam in (0.0, 0.2, 1.0):
            assert abs(tournament_payoff(s, stacks, [50.0, 30.0, 20.0], lam).sum()) < 1e-9
    assert busts > 5


def test_equal_stacks_busting_together_share_places():
    stacks, payouts = [5000, 1000, 1000], [50.0, 30.0, 20.0]
    s = _allin_hand(stacks, shover=0, callers={1, 2}, winner=0)
    r = tournament_payoff(s, stacks, payouts)
    before = np.array(icm_equity(stacks, payouts))
    assert r == pytest.approx(np.array([50.0, 25.0, 25.0]) - before, abs=1e-9)


def test_players_busted_earlier_get_zero():
    stacks = [3000, 2000, 1000]
    s = _allin_hand(stacks, shover=0, callers={2}, winner=0)
    payouts = [50.0, 30.0, 20.0, 10.0, 5.0]
    table = [0, 3000, 0, 2000, 1000]
    r = tournament_payoff(s, table, payouts, lam=0.3)
    assert r[[0, 2]].tolist() == [0.0, 0.0]
    assert r[[1, 3, 4]] == pytest.approx(tournament_payoff(s, stacks, payouts, lam=0.3), abs=1e-12)


def test_rejects_out_of_scope_and_mismatched_input():
    s = _allin_hand([3000, 2000, 1000], shover=0, callers={2}, winner=0)
    with pytest.raises(ValueError, match="exact ICM limit"):
        tournament_payoff(s, [1000] * 10, [50.0, 30.0, 20.0])
    with pytest.raises(ValueError, match="do not match"):
        tournament_payoff(s, [3000, 2000, 900], [50.0, 30.0, 20.0])
    with pytest.raises(ValueError, match="integer"):
        tournament_payoff(s, [3000.0, 2000.0, 1000.0], [50.0, 30.0, 20.0])
    with pytest.raises(ValueError, match="not over"):
        tournament_payoff(game.deal(np.random.default_rng(2), n=3), [game.STACK] * 3, [50.0, 30.0])


def test_six_handed_call_time_reference(capsys):
    stacks = [4000, 2500, 6000, 1500, 3000, 5000]
    s = game.random_playout(np.random.default_rng(3), n=6, stacks=tuple(stacks))
    payouts = [50.0, 30.0, 20.0]
    reps = 50
    t0 = time.perf_counter()
    for _ in range(reps):
        tournament_payoff(s, stacks, payouts)
    per_call = (time.perf_counter() - t0) / reps
    with capsys.disabled():
        print(f"\n[reference only, no threshold] tournament_payoff 6-handed: {per_call * 1e3:.3f} ms/call")
