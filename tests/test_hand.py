import numpy as np
import pytest

from stalker.tournament.hand import Hand, parse_phh, replay_phh_final_stacks


def _random_hand(rng: np.random.Generator) -> tuple[Hand, dict]:
    n_seats = int(rng.integers(2, 11))
    stacks = [int(rng.integers(1, 400)) for _ in range(n_seats)]
    occupied = rng.random(n_seats) < 0.8
    stacks = [s if o else 0 for s, o in zip(stacks, occupied)]
    while sum(s > 0 for s in stacks) < 2:
        stacks[int(rng.integers(n_seats))] = int(rng.integers(1, 400))
    button = int(rng.choice([i for i, s in enumerate(stacks) if s > 0]))
    mode = str(rng.choice(["none", "classic", "bb_ante"]))
    ante = 0 if mode == "none" else int(rng.integers(1, 4))
    sb = int(rng.integers(1, 4))
    kw = dict(stacks=stacks, button=button, small_blind=sb, big_blind=2 * sb, ante=ante, ante_mode=mode)
    return Hand(rng=np.random.default_rng(int(rng.integers(2**32))), **kw), kw


def _play_random(hand: Hand, rng: np.random.Generator) -> None:
    while not hand.is_over:
        la = hand.legal_actions()
        r = rng.random()
        if la.can_fold and r < 0.2:
            hand.fold()
        elif la.min_raise_to is not None and r > 0.75:
            hand.raise_to(int(rng.integers(la.min_raise_to, la.max_raise_to + 1)))
        else:
            hand.check_or_call()


def test_invariants_random_hands():
    rng = np.random.default_rng(20261023)
    for _ in range(1000):
        hand, kw = _random_hand(rng)
        _play_random(hand, rng)
        res = hand.result()
        assert sum(res.final_stacks) == sum(kw["stacks"])
        assert min(res.final_stacks) >= 0
        assert sum(res.deltas) == 0
        pot_total = sum(p.amount for p in res.pots)
        assert sum(a.amount for a in res.awards) == pot_total
        for award in res.awards:
            assert sum(award.awards.values()) == award.amount
        won = {}
        for award in res.awards:
            for seat, amt in award.awards.items():
                won[seat] = won.get(seat, 0) + amt
        # Each seat can win at most what the pots it is eligible for hold (side-pot correctness).
        for seat, amt in won.items():
            assert amt <= sum(p.amount for p in res.pots if seat in p.eligible)
        # Pots = everything put in minus refunded uncalled bets = what the table lost plus what winners got back.
        assert pot_total == sum(won.values())
        for seat, s in enumerate(kw["stacks"]):
            if s == 0:
                assert res.final_stacks[seat] == 0


def test_same_seed_same_actions_same_result():
    rng = np.random.default_rng(7)
    for _ in range(50):
        hand, kw = _random_hand(rng)
        seed = int(rng.integers(2**32))
        hand = Hand(rng=np.random.default_rng(seed), **kw)
        _play_random(hand, rng)
        replay = Hand(rng=np.random.default_rng(seed), **kw)
        for seat, kind, amount in hand.actions():
            assert replay.actor == seat
            {"f": lambda: replay.fold(), "cc": lambda: replay.check_or_call(),
             "cbr": lambda: replay.raise_to(amount)}[kind]()
        assert replay.is_over
        assert replay.result() == hand.result()
        assert replay.board() == hand.board()
        assert replay.to_phh() == hand.to_phh()


def test_different_seed_deals_differently():
    kw = dict(stacks=[100] * 6, button=0, small_blind=1, big_blind=2)
    a = Hand(rng=np.random.default_rng(1), **kw)
    b = Hand(rng=np.random.default_rng(2), **kw)
    assert [a.hole_cards(s) for s in range(6)] != [b.hole_cards(s) for s in range(6)]


def test_phh_roundtrip():
    rng = np.random.default_rng(99)
    for _ in range(100):
        hand, _ = _random_hand(rng)
        _play_random(hand, rng)
        text = hand.to_phh()
        hh = parse_phh(text)
        assert hh.dumps() == text
        assert replay_phh_final_stacks(text) == hand.result().final_stacks


def test_heads_up_button_posts_small_blind_and_acts_first():
    hand = Hand([50, 60], button=0, small_blind=1, big_blind=2, rng=np.random.default_rng(0))
    assert hand.actor == 0
    la = hand.legal_actions()
    assert la.call_amount == 1 and la.min_raise_to == 4 and la.max_raise_to == 50


def test_bb_ante_only_bb_pays():
    # seats: 0=button, 1=SB, 2=BB, 3=UTG
    hand = Hand([100] * 4, button=0, small_blind=1, big_blind=2, ante=2, ante_mode="bb_ante",
                rng=np.random.default_rng(0))
    for _ in range(3):
        hand.fold()
    res = hand.result()
    assert res.deltas == (0, -1, 1, 0)  # BB wins SB's blind; its own ante+blind come back


def test_classic_ante_everyone_pays():
    hand = Hand([100] * 3, button=0, small_blind=1, big_blind=2, ante=1, ante_mode="classic",
                rng=np.random.default_rng(0))
    hand.fold()  # button
    hand.fold()  # SB
    assert hand.result().deltas == (-1, -2, 3)


def test_short_all_in_and_side_pots():
    # Seat 0 (10 chips) all-in and called by two deeper stacks -> main + side pot.
    hand = Hand([10, 100, 100], button=0, small_blind=1, big_blind=2, rng=np.random.default_rng(3))
    hand.raise_to(10)
    hand.check_or_call()
    hand.check_or_call()
    while not hand.is_over:
        la = hand.legal_actions()
        if la.min_raise_to is not None:
            hand.raise_to(la.max_raise_to)
        else:
            hand.check_or_call()
    res = hand.result()
    assert sum(p.amount for p in res.pots) == 210
    assert res.pots[0].amount == 30 and set(res.pots[0].eligible) == {0, 1, 2}
    assert res.pots[1].amount == 180 and set(res.pots[1].eligible) == {1, 2}
    assert res.final_stacks[0] in (0, 30, 10, 15)


def test_rejects_bad_input():
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError):
        Hand([100, 0], button=0, small_blind=1, big_blind=2, rng=rng)
    with pytest.raises(ValueError):
        Hand([100, 100], button=1, small_blind=1, big_blind=2, ante=1, rng=rng)
    with pytest.raises(ValueError):
        Hand([0, 100, 100], button=0, small_blind=1, big_blind=2, rng=rng)
    hand = Hand([100, 100], button=0, small_blind=1, big_blind=2, rng=rng)
    with pytest.raises(ValueError, match="legal_actions"):
        hand.raise_to(3)
    with pytest.raises(RuntimeError):
        hand.result()
