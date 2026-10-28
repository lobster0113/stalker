"""Property tests (hypothesis) for the NLHE engines: random action sequences must keep the rule invariants.

Both `Hand` (PokerKit) and `FastHand` are driven with the same generated hands (#120). Profiles are
derandomized so CI is deterministic; a failing example prints the seed/stacks/choices to replay it.
"""
from __future__ import annotations

import numpy as np
import pytest
from hypothesis import HealthCheck, example, given, settings, strategies as st

from stalker.tournament.fast_hand import FastHand
from stalker.tournament.hand import Hand

ENGINES = [Hand, FastHand]
MAX_STEPS = 150

settings.register_profile(
    "engine", max_examples=120, deadline=None, derandomize=True, suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile("engine")


@st.composite
def hands(draw):
    n_seats = draw(st.integers(2, 9))
    stacks = draw(st.lists(st.integers(0, 600), min_size=n_seats, max_size=n_seats))
    occupied = [i for i, s in enumerate(stacks) if s > 0]
    if len(occupied) < 2:  # keep the example valid rather than filtering it away
        stacks[0], stacks[1] = max(stacks[0], 1), max(stacks[1], 1)
        occupied = [i for i, s in enumerate(stacks) if s > 0]
    button = draw(st.sampled_from(occupied))
    bb = draw(st.integers(1, 40))
    sb = draw(st.integers(1, bb))
    ante_mode = draw(st.sampled_from(["none", "classic", "bb_ante"]))
    ante = 0 if ante_mode == "none" else draw(st.integers(1, 10))
    seed = draw(st.integers(0, 2**32 - 1))
    # (action kind, raise fraction): kind 0 fold, 1-3 call, 4 min-raise, 5 shove, 6 random raise.
    choices = draw(st.lists(st.tuples(st.integers(0, 6), st.floats(0, 1)), max_size=MAX_STEPS))
    return dict(stacks=stacks, button=button, small_blind=sb, big_blind=bb, ante=ante, ante_mode=ante_mode,
                seed=seed, choices=choices)


def _new(engine, spec, rotate=0):
    n = len(spec["stacks"])
    stacks = [spec["stacks"][(i - rotate) % n] for i in range(n)]
    return engine(stacks, (spec["button"] + rotate) % n, spec["small_blind"], spec["big_blind"],
                  np.random.default_rng(spec["seed"]), ante=spec["ante"], ante_mode=spec["ante_mode"])


def _play(h, spec, on_step=None):
    """Drive `h` to the end with the generated choices, then calls."""
    for kind, frac in spec["choices"]:
        if h.is_over:
            return
        la = h.legal_actions()
        if on_step:
            on_step(h, la)
        if kind == 0 and la.can_fold:
            h.fold()
        elif kind <= 3 or la.min_raise_to is None:
            h.check_or_call()
        else:
            lo, hi = la.min_raise_to, la.max_raise_to
            to = lo if kind == 4 else hi if kind == 5 else lo + int(frac * (hi - lo))
            h.raise_to(to)
    while not h.is_over:  # choices exhausted: everyone calls down
        if on_step:
            on_step(h, h.legal_actions())
        h.check_or_call()


@pytest.mark.parametrize("engine", ENGINES)
@given(spec=hands())
def test_chips_conserved(engine, spec):
    h = _new(engine, spec)
    _play(h, spec)
    r = h.result()
    assert sum(r.final_stacks) == sum(r.starting_stacks)
    assert sum(r.deltas) == 0
    assert all(s >= 0 for s in r.final_stacks)
    for seat, s in enumerate(spec["stacks"]):
        if s == 0:
            assert r.final_stacks[seat] == 0


@pytest.mark.parametrize("engine", ENGINES)
@given(spec=hands())
def test_only_legal_actions_apply(engine, spec):
    def check(h, la):
        assert la.seat == h.actor
        assert la.call_amount >= 0
        if la.min_raise_to is not None:
            assert la.min_raise_to <= la.max_raise_to
            for bad in (la.min_raise_to - 1, la.max_raise_to + 1):
                with pytest.raises(ValueError):
                    h.raise_to(bad)
        else:
            with pytest.raises(ValueError):
                h.raise_to(10**6)
        if la.call_amount == 0:
            with pytest.raises(ValueError):
                h.fold()

    h = _new(engine, spec)
    _play(h, spec, on_step=check)
    assert h.is_over and h.actor is None


def _max_posted_blind(spec):
    """Largest blind actually posted preflop; blinds are capped by the stack left after the ante."""
    n_seats = len(spec["stacks"])
    order = [s for s in ((spec["button"] + 1 + k) % n_seats for k in range(n_seats)) if spec["stacks"][s] > 0]
    heads_up = len(order) == 2
    bb_seat, sb_seat = (order[0], order[1]) if heads_up else (order[1], order[0])
    ante = {s: 0 for s in order}
    if spec["ante_mode"] == "classic":
        ante = {s: min(spec["ante"], spec["stacks"][s]) for s in order}
    elif spec["ante_mode"] == "bb_ante":
        ante[bb_seat] = min(spec["ante"], spec["stacks"][bb_seat])
    return max(
        min(blind, spec["stacks"][seat] - ante[seat])
        for seat, blind in ((sb_seat, spec["small_blind"]), (bb_seat, spec["big_blind"]))
    )


@pytest.mark.parametrize("engine", ENGINES)
@given(spec=hands())
# #204: short BB posts 1 all in, UTG goes all in for 2 (not a full raise), BTN raises to 4. The full raise
# is measured from 2, so the next minimum is 6 — the old oracle measured it from the posted 1 and said 7.
@example(spec={"stacks": [0, 0, 2, 5, 7, 1], "button": 3, "small_blind": 1, "big_blind": 2, "ante": 0,
               "ante_mode": "none", "seed": 0, "choices": [(4, 0.0), (4, 0.0)]})
def test_min_raise_rule(engine, spec):
    """Min raise-to = current level + largest full raise so far (or all-in), tracked from the actions applied.

    Preflop the level is only known once a full raise has been made (short blinds can leave it below the BB);
    postflop it starts at 0 with a minimum bet of one BB.
    """
    bb = spec["big_blind"]
    posted = _max_posted_blind(spec)
    # `cur` is the bet to match so far: a short all-in that is not a full raise still raises it, and the
    # first full raise is measured from it (both engines and PokerKit agree; #204).
    state = {"street": 0, "level": bb if posted >= bb else None, "inc": bb, "cur": max(posted, 0)}
    seen = 0

    def step(h, la):
        nonlocal seen
        street = len(h.board())
        if street != state["street"]:
            state.update(street=street, level=0, inc=bb)
        for _, kind, amount in h.actions()[seen:]:
            if kind != "cbr":
                continue
            if state["level"] is None:
                if amount - state["cur"] >= bb:  # first preflop raise that is certainly a full one
                    state.update(level=amount, inc=amount - state["cur"])
                state["cur"] = max(state["cur"], amount)
                continue
            if amount - state["level"] >= state["inc"]:
                state["inc"] = amount - state["level"]
            state["level"] = max(state["level"], amount)
        seen = len(h.actions())
        if la.min_raise_to is None or state["level"] is None:
            return
        assert la.min_raise_to == min(la.max_raise_to, state["level"] + state["inc"]), (la, state)

    h = _new(engine, spec)
    _play(h, spec, on_step=step)


def _independent_contributions(spec, steps):
    """Per-seat chips put in the pot, from the spec and the applied actions only (never from engine results).

    Blinds/antes follow the ruleset in `fast_hand.py` (capped by stack after ante; heads-up the button is SB).
    Calls use the `cc` amount, raises use `cbr` raise-to minus what the seat already committed this street.
    Refund (PokerKit convention, mirrored by both engines): bets of the last betting street are not yet in a pot
    when the hand ends, so the uncalled part of the top bet (top minus runner-up) goes back to its owner, and a
    sole survivor of folds gets their whole bet of that street back. Antes are never refunded.
    """
    n_seats = len(spec["stacks"])
    order = [s for s in ((spec["button"] + 1 + k) % n_seats for k in range(n_seats)) if spec["stacks"][s] > 0]
    heads_up = len(order) == 2
    bb_seat = order[0] if heads_up else order[1]
    sb_seat = order[1] if heads_up else order[0]
    ante = {s: 0 for s in order}
    if spec["ante_mode"] == "classic":
        ante = {s: min(spec["ante"], spec["stacks"][s]) for s in order}
    elif spec["ante_mode"] == "bb_ante":
        ante[bb_seat] = min(spec["ante"], spec["stacks"][bb_seat])
    street_bet = {s: 0 for s in order}
    for seat, blind in ((sb_seat, spec["small_blind"]), (bb_seat, spec["big_blind"])):
        street_bet[seat] = min(blind, spec["stacks"][seat] - ante[seat])
    bets = dict(street_bet)
    cur_street, folded = 0, set()
    for street, seat, kind, amount in steps:
        if street != cur_street:
            cur_street, street_bet = street, {s: 0 for s in order}
        if kind == "f":
            folded.add(seat)
        elif kind == "cc":
            street_bet[seat] += amount
            bets[seat] += amount
        elif kind == "cbr":
            bets[seat] += amount - street_bet[seat]
            street_bet[seat] = amount
    top = sorted(street_bet.values(), reverse=True)
    alive = [x for x in order if x not in folded]
    refund_to, refund = max(street_bet, key=street_bet.get), top[0] - top[1]
    if len(alive) == 1:
        refund_to, refund = alive[0], street_bet[alive[0]]
    contrib = [0] * n_seats
    for x in order:
        contrib[x] = ante[x] + bets[x] - (refund if x == refund_to else 0)
    return contrib


@pytest.mark.parametrize("engine", ENGINES)
@given(spec=hands())
def test_pot_equals_contributions(engine, spec):
    h = _new(engine, spec)
    steps, seen, street = [], 0, 0

    def track(h, la):
        nonlocal seen, street
        for seat, kind, amount in h.actions()[seen:]:  # made in the street seen at the previous step
            steps.append((street, seat, kind, amount))
        seen = len(h.actions())
        street = len(h.board())

    _play(h, spec, on_step=track)
    for seat, kind, amount in h.actions()[seen:]:
        steps.append((street, seat, kind, amount))
    r = h.result()
    expected = _independent_contributions(spec, steps)
    won_by_seat = [0] * len(spec["stacks"])
    for a in r.awards:
        for seat, chips in a.awards.items():
            won_by_seat[seat] += chips
    assert sum(p.amount for p in r.pots) == sum(a.amount for a in r.awards) == sum(expected)
    for seat in range(len(spec["stacks"])):
        assert expected[seat] == r.starting_stacks[seat] - r.final_stacks[seat] + won_by_seat[seat], (seat, expected)
    for p in r.pots:
        assert p.amount > 0 and p.eligible and all(spec["stacks"][s] > 0 for s in p.eligible)


@pytest.mark.parametrize("engine", ENGINES)
@given(spec=hands(), rotate=st.integers(1, 8))
def test_seat_rotation_invariant(engine, spec, rotate):
    base = _new(engine, spec)
    _play(base, spec)
    rot = _new(engine, spec, rotate)
    _play(rot, spec)
    n = len(spec["stacks"])
    b, r = base.result(), rot.result()
    assert tuple(r.deltas[(i + rotate) % n] for i in range(n)) == b.deltas
    assert sorted(p.amount for p in r.pots) == sorted(p.amount for p in b.pots)
    def award_key(a, shift):
        return a.amount, tuple(sorted(((seat + shift) % n, chips) for seat, chips in a.awards.items()))

    assert sorted(award_key(a, rotate) for a in b.awards) == sorted(award_key(a, 0) for a in r.awards)
