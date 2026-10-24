import numpy as np
import pytest

from referee.anchors import icm_reference as ir
from referee.anchors.hu_equity import N_CLASSES, evaluate_batch, load
from stalker.core.cards import HAND_CLASSES, cards
from stalker.core.evaluator import evaluate

H = HAND_CLASSES.index


def test_evaluate_batch_matches_scalar_evaluator():
    rng = np.random.default_rng(7)
    hands = np.array([rng.choice(52, 7, replace=False) for _ in range(5000)])
    edge = [cards(t) for t in ("AsKsQsJsTs2c3d", "As2s3s4s5s9h9d", "AhAdAcAs2c2d3h",
                               "KhKdKc2s2c2d3h", "Ah2d3c4s5h9d9c", "7h7d5c5s3h3d2c",
                               "AhKdQc9s7h5d3c", "9h9d9cKs7h4d2c")]
    hands = np.vstack([hands, np.array(edge)])
    assert evaluate_batch(hands).tolist() == [evaluate(list(h)) for h in hands]


def test_equity_table_consistency():
    E, N = load()
    assert E.shape == N.shape == (N_CLASSES, N_CLASSES)
    np.testing.assert_allclose(E + E.T, 1.0, atol=1e-9)
    combos = ir.CLASS_COMBOS
    np.testing.assert_array_equal(N.sum(axis=1), combos * 1225)
    assert N[H("AA"), H("AA")] == 6 and N[H("AKs"), H("AKs")] == 12  # 4 suits x 3 other suits
    # Well-known all-in matchups (any equity calculator): AA-KK 81.9%, AKo-22 ~47%, AKs-QJs ~63.5%.
    assert abs(E[H("AA"), H("KK")] - 0.819) < 0.006
    assert abs(E[H("AKo"), H("22")] - 0.47) < 0.012
    assert abs(E[H("AKs"), H("QJs")] - 0.635) < 0.01


@pytest.mark.parametrize("spot", [
    ir.Spot((3000, 2500, 1800, 900), 50, 100, (50, 30, 20), ante=10),
    ir.Spot((1500, 800, 2200), 25, 50, (60, 40), bb_ante=50),
    ir.Spot((1000, 400), 10, 20),
])
def test_terminal_stacks_conserve_chips(spot):
    total = sum(spot.stacks)
    assert ir.terminal_stacks(spot, None).sum() == total
    for p in range(spot.n - 1):
        assert ir.terminal_stacks(spot, p).sum() == total
        for q in range(p + 1, spot.n):
            for w in (p, q):
                out = ir.terminal_stacks(spot, p, q, w)
                assert out.sum() == pytest.approx(total)
                assert out.min() >= 0
                loser = q if w == p else p
                m = min(spot.stacks[p] - spot.dead[p], spot.stacks[q] - spot.dead[q])
                assert out[loser] == spot.stacks[loser] - spot.dead[loser] - m


def test_spot_rejects_unsupported_inputs():
    with pytest.raises(ir.SpotError, match="2..9"):
        ir.Spot((100,), 1, 2)
    with pytest.raises(ir.SpotError, match="chips behind"):
        ir.Spot((100, 20), 10, 20)
    with pytest.raises(ir.SpotError, match="not both"):
        ir.Spot((100, 100), 1, 2, ante=1, bb_ante=2)


def test_busted_seat_takes_its_place_payout():
    v = ir._place_values(np.array([600.0, 0.0, 400.0]), (50, 30, 20))
    assert v[1] == 20
    assert v.sum() == pytest.approx(100)


def _hu10(model="chipev"):
    return ir.solve(ir.Spot((200, 200), 10, 20), value_model=model, tol=1e-5, max_iter=20000)


def test_hu_10bb_chipev_matches_public_nash_chart():
    # HoldemResources HU push/fold Nash charts (holdemresources.net, no ante, 10bb effective):
    # SB pushes ~58% of hands, BB calls ~37%. Edge hands: SB pushes K2o and Q7o, folds 72o;
    # BB calls A2o, K9o and folds Q5o. A tight tol is needed: at 1e-3 the averaged ranges are
    # still blurred at the edges even though the exploitability bound already holds.
    sol = _hu10()
    assert sol.converged
    assert 0.56 <= sol.push_freq(0) <= 0.60
    assert 0.35 <= sol.call_freq(1, 0) <= 0.39
    push, call = sol.push_range(0), sol.call_range(1, 0)
    for c in ("AA", "22", "A2o", "K2o", "Q8o", "J7s", "T9s", "54s"):
        assert push[c] > 0.9, c
    for c in ("72o", "83o", "42o"):
        assert push[c] < 0.1, c
    for c in ("AA", "22", "A2o", "K9o", "QTo", "J9s"):
        assert call[c] > 0.9, c
    for c in ("72o", "Q5o", "96o"):
        assert call[c] < 0.1, c


def test_converges_within_tenth_of_percent_of_pool():
    spot = ir.Spot((4000, 2500, 1500, 3500, 1200, 2300), 50, 100, (50, 30, 20), ante=10)
    sol = ir.solve(spot)
    assert sol.converged
    assert sol.gains.max() <= 1e-3 * spot.prize_pool
    assert sol.value.sum() == pytest.approx(spot.prize_pool)


def test_winner_take_all_equals_chipev():
    spot = ir.Spot((3000, 2000, 1500, 1000), 50, 100, (1.0,), ante=10)
    icm = ir.solve(spot, value_model="icm", tol=2e-4)
    chip = ir.solve(spot, value_model="chipev", tol=2e-4)
    for p in range(spot.n - 1):
        assert abs(icm.push_freq(p) - chip.push_freq(p)) < 0.01
        for q in range(p + 1, spot.n):
            assert abs(icm.call_freq(q, p) - chip.call_freq(q, p)) < 0.01
    np.testing.assert_allclose(icm.value, chip.value / sum(spot.stacks), atol=2e-3)


def test_bubble_tightens_calling_ranges():
    # 4 left, 3 paid: calling an all-in risks the bubble, so ICM calls must be narrower.
    spot = ir.Spot((2000, 2000, 2000, 2000), 100, 200, (50, 30, 20))
    icm = ir.solve(spot)
    chip = ir.solve(spot, value_model="chipev")
    for p in range(3):
        for q in range(p + 1, 4):
            assert icm.call_freq(q, p) < chip.call_freq(q, p) - 0.05
    assert icm.call_freq(3, 2) < 0.75 * chip.call_freq(3, 2)


@pytest.mark.slow
def test_fgs_depth_one_differs_from_icm():
    spot = ir.Spot((900, 3000, 2100), 100, 200, (65, 35), ante=20)
    d0 = ir.solve(spot)
    d1 = ir.solve(spot, fgs_depth=1)
    assert d1.converged
    assert d1.value.sum() == pytest.approx(spot.prize_pool)
    diffs = [abs(d0.push_freq(p) - d1.push_freq(p)) for p in range(2)]
    diffs += [abs(d0.call_freq(q, p) - d1.call_freq(q, p)) for p in range(2) for q in range(p + 1, 3)]
    assert max(diffs) > 0.02
    assert np.abs(d0.value - d1.value).max() > 1e-3 * spot.prize_pool


def test_evaluate_spot_against_nash_and_profile():
    spot = ir.Spot((2500, 1500, 3000, 1000), 50, 100, (50, 30, 20), ante=10)
    nash = ir.solve(spot)
    hero = 1

    def nash_policy(s, seat, pusher):
        return nash.strategy.push[seat] if pusher is None else nash.strategy.call[seat, pusher]

    def always_push(s, seat, pusher):
        return np.ones(N_CLASSES)

    r = ir.evaluate_spot(nash_policy, spot, nash, hero)
    assert r["ev"] == pytest.approx(nash.value[hero])
    assert r["loss"] <= 1e-3 * spot.prize_pool
    bad = ir.evaluate_spot(always_push, spot, nash, hero)
    assert bad["loss"] > 5e-3 * spot.prize_pool
    assert bad["ev"] < r["ev"]
    assert bad["best_response_ev"] == pytest.approx(r["best_response_ev"])

    loose = ir.top_percent_strategy(spot.n, 0.6, 0.5)
    exploit = ir.evaluate_spot(nash_policy, spot, loose, hero)
    assert exploit["loss"] > 0
    with pytest.raises(ir.SpotError, match="169 probabilities"):
        ir.evaluate_spot(lambda s, seat, p: np.ones(3), spot, nash, hero)


def test_evaluate_spot_rejects_solution_of_another_spot():
    spot = ir.Spot((2500, 1500, 3000), 50, 100, (50, 30, 20))
    other = ir.Spot((2500, 1600, 3000), 50, 100, (50, 30, 20))
    nash = ir.solve(other)

    def policy(s, seat, pusher):
        return np.ones(N_CLASSES)

    with pytest.raises(ir.SpotError, match="stacks"):
        ir.evaluate_spot(policy, spot, nash, 1)
    payout = ir.solve(ir.Spot(spot.stacks, 50, 100, (60, 40, 0)))
    with pytest.raises(ir.SpotError, match="payouts"):
        ir.evaluate_spot(policy, spot, payout, 1)
    blinds = ir.solve(ir.Spot(spot.stacks, 25, 50, (50, 30, 20)))
    with pytest.raises(ir.SpotError, match="sb 25 != 50"):
        ir.evaluate_spot(policy, spot, blinds, 1)


@pytest.mark.parametrize("kwargs", [
    dict(stacks=(1500.5, 2000), sb=50, bb=100),
    dict(stacks=(1500, 2000), sb=50.0, bb=100),
    dict(stacks=(1500, 2000), sb=50, bb=100, ante=1.5),
    dict(stacks=(1500, 2000), sb=50, bb=100, bb_ante=100.0),
    dict(stacks=(1500, True), sb=50, bb=100),
])
def test_spot_requires_integer_chips(kwargs):
    with pytest.raises(ir.SpotError, match="integer"):
        ir.Spot(**kwargs)


def test_spot_accepts_numpy_integers_and_exposes_baseline_tol():
    spot = ir.Spot(tuple(np.array([1500, 2000])), np.int64(50), 100)
    assert spot.stacks == (1500, 2000) and type(spot.sb) is int
    assert 0 < ir.BASELINE_TOL <= 1e-3
