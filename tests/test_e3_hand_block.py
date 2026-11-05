"""`hand_block` per-node cost (#508): combo card indexes built once, the near-nut mask cached per board and
the per-card mass taken by one `bincount`; every value must equal the pre-#508 code, nan positions included."""
import numpy as np

from stalker.core.cards import COMBOS, N_CARDS
from stalker.e3 import game as G
from stalker.e3 import tp_key as K


def _hand_block_before(s, seat, ranges):
    """`hand_block` as on main c49601d (before #508)."""
    if s.street == 0:
        return None
    strength = K._equity_cached(tuple(s.board), K._UNIFORM)
    ok = ~np.isnan(strength)
    top = ok & (strength >= np.quantile(strength[ok], 1 - K.NUT_TOP))
    pair = np.array(COMBOS)
    out = []
    for q in s.live():
        if q == seat:
            continue
        m = ranges[q] * top
        total = m.sum()
        card_mass = np.zeros(N_CARDS)
        np.add.at(card_mass, pair[:, 0], m)
        np.add.at(card_mass, pair[:, 1], m)
        r = np.where(ok, (card_mass[pair[:, 0]] + card_mass[pair[:, 1]] - m) / total, np.nan) if total > 0 else np.zeros(K.N)
        avg = np.nanmean(np.where(ok, r, np.nan))
        den = r + avg
        out.append(np.where(den > 0, 100.0 * r / np.where(den > 0, den, 1.0), 50.0))
    if not out:
        return None
    v = np.mean(out, axis=0)
    v[~ok] = np.nan
    return v


def _spot(rng, n, street):
    s = G.deal(rng, n)
    folded = tuple(bool(rng.random() < 0.4) for _ in range(n))
    if sum(not f for f in folded) < 2:
        folded = (False, False) + folded[2:]
    return s._replace(street=street, board=s.deck[:2 + street], folded=folded)


def _ranges(rng, n):
    out = []
    for _ in range(n):
        w = rng.random(K.N) * (rng.random(K.N) < rng.uniform(0.05, 1.0))
        if rng.random() < 0.1:
            w[:] = 0.0   # no near-nut mass: the neutral branch
        out.append(w)
    return out


def test_hand_block_equals_the_pre_508_code_bit_for_bit():
    rng = np.random.default_rng(508)
    for t in range(60):
        n = 2 + t % 5
        s = _spot(rng, n, 1 + t % 3)
        ranges = _ranges(rng, n)
        for seat in s.live():
            got, want = K.hand_block(s, seat, ranges), _hand_block_before(s, seat, ranges)
            assert got is not None and want is not None
            assert np.array_equal(got, want, equal_nan=True), (t, seat)
            assert np.array_equal(np.isnan(got), np.isnan(want))


def test_hand_block_is_none_preflop():
    rng = np.random.default_rng(1)
    s = G.deal(rng, 6)
    assert K.hand_block(s, 0, _ranges(rng, 6)) is None


def test_card_mass_equals_two_add_at_passes():
    rng = np.random.default_rng(3)
    pair = np.array(COMBOS)
    for _ in range(50):
        m = rng.random(K.N) * (rng.random(K.N) < 0.5) * 10.0 ** rng.uniform(-8, 3)
        want = np.zeros(N_CARDS)
        np.add.at(want, pair[:, 0], m)
        np.add.at(want, pair[:, 1], m)
        assert np.array_equal(K._card_mass(m), want)


def test_near_nut_is_cached_per_board_and_read_only():
    K._NUT_CACHE.clear()
    board = (0, 13, 26)
    ok, top = K._near_nut(board)
    assert K._near_nut(board)[1] is top and len(K._NUT_CACHE) == 1
    assert not ok.flags.writeable and not top.flags.writeable
    K._near_nut((0, 13, 27))
    assert len(K._NUT_CACHE) == 2
