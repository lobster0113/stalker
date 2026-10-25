import time

import numpy as np
import pytest

from referee.agents import reference_bot as rb
from referee.agents.reference_bot import (REFERENCE_BOT_VERSION, ReferenceBot, factory, hand_start_stacks,
                                          load_chart, preflop_order, solve_ranges)
from referee.anchors.icm_reference import Spot, _Tree, _value_fn, evaluate_spot, solve
from referee.evaluate import evaluate
from stalker.agents.base import Action, Agent, Observation
from stalker.agents.random_agent import RandomLegalAgent
from stalker.core.cards import HAND_CLASSES
from stalker.tournament.config import load_preset
from stalker.tournament.director import run_game
from stalker.tournament.hand import LegalActions


def _obs(stacks, bets, seat, button, hole, *, board=(), history=(), sb=50, bb=100, ante=0, dead=0,
         players_remaining=None, call=None, in_hand=None):
    """Hand-built observation; `stacks` are chips behind, `dead` the antes already in the pot."""
    top = max(bets.values())
    call = top - bets[seat] if call is None else call
    own = stacks[seat] + bets[seat]
    can_raise = stacks[seat] > call
    la = LegalActions(seat, call > 0, min(call, stacks[seat]), min(top + bb, own) if can_raise else None,
                      own if can_raise else None)
    return Observation(
        game_id="g", tournament_id="t", hand_id=1, hand_no=1, table_id=0, player_id=seat, seat=seat,
        button=button, hole_cards=tuple(hole), board=tuple(board), pot=sum(bets.values()) + dead,
        stacks=dict(stacks), bets=dict(bets), in_hand=tuple(in_hand or sorted(stacks)),
        seat_players={s: s for s in stacks}, sb=sb, bb=bb, ante=ante, next_blinds=None,
        players_remaining=players_remaining or len(stacks), paid_places=1, legal=la,
        action_history=tuple(history), all_stacks=tuple(sorted(stacks.values(), reverse=True)),
        hand_start_stack=own)


def test_version_names_every_component():
    v = REFERENCE_BOT_VERSION
    assert v.startswith("refbot-v1") and load_chart()["version"] in v
    assert rb.ICM_REFERENCE_VERSION in v and rb.POSTFLOP_VERSION in v and "short15bb" in v
    assert ReferenceBot.version == v


def test_preflop_order_ends_with_blinds():
    o = _obs({s: 1000 for s in range(6)}, {s: 0 for s in range(6)}, 0, button=1, hole=("As", "Kd"))
    assert preflop_order(o) == [4, 5, 0, 1, 2, 3]
    hu = _obs({0: 1000, 1: 1000}, {0: 50, 1: 100}, 0, button=0, hole=("As", "Kd"))
    assert preflop_order(hu) == [0, 1]  # button posts the SB and acts first


@pytest.mark.parametrize("ante,dead,exp_ante,exp_bb_ante", [(10, 30, 10, 0), (30, 30, 0, 30), (0, 0, 0, 0)])
def test_hand_start_stacks_recovers_posts(ante, dead, exp_ante, exp_bb_ante):
    # 3-handed, button 0 -> SB 1, BB 2; posts already taken from the stacks.
    stacks = {0: 1000 - exp_ante, 1: 1000 - exp_ante - 50, 2: 1000 - exp_ante - exp_bb_ante - 100}
    o = _obs(stacks, {0: 0, 1: 50, 2: 100}, 0, button=0, hole=("As", "Kd"), ante=ante, dead=dead)
    order = preflop_order(o)
    start, a, b = hand_start_stacks(o, order)
    assert (a, b) == (exp_ante, exp_bb_ante)
    assert start == {0: 1000, 1: 1000, 2: 1000}


def _short_first_in(hole, bb_stack=1000):
    # 3-handed final table, everyone 10bb; button (seat 0) first in.
    stacks = {0: 1000, 1: 950, 2: bb_stack - 100}
    return _obs(stacks, {0: 0, 1: 50, 2: 100}, 0, button=0, hole=hole)


def test_short_stack_first_in_uses_icm_reference_push_range():
    payouts = (0.5, 0.3, 0.2)
    bot = ReferenceBot(np.random.default_rng(0), payouts)
    sol = solve_ranges(Spot((200, 200, 200), 10, 20, payouts), "icm")
    for hole, cls in ((("Ah", "Ad"), "AA"), (("7c", "2d"), "72o"), (("Ts", "9s"), "T9s")):
        probs = bot.action_probs(_short_first_in(hole))
        p = sol.push[0, HAND_CLASSES.index(cls)]
        assert probs.get(Action("raise", 1000), 0.0) == pytest.approx(p)
        assert sum(probs.values()) == pytest.approx(1.0)
    assert bot.action_probs(_short_first_in(("Ah", "Ad"))) == {Action("raise", 1000): 1.0}
    assert bot.action_probs(_short_first_in(("7c", "2d"))) == {Action("fold"): 1.0}


def test_short_stack_call_uses_icm_reference_call_range():
    payouts = (0.5, 0.3, 0.2)
    bot = ReferenceBot(np.random.default_rng(0), payouts)
    sol = solve_ranges(Spot((200, 200, 200), 10, 20, payouts), "icm")
    # Button shoved 10bb, SB folded, BB (seat 2) decides.
    stacks = {0: 0, 1: 950, 2: 900}
    hist = ((0, "cbr", 1000), (1, "f", 0))
    for hole, cls in ((("Kh", "Kd"), "KK"), (("8c", "3d"), "83o"), (("Ac", "9d"), "A9o")):
        o = _obs(stacks, {0: 1000, 1: 50, 2: 100}, 2, button=0, hole=hole, history=hist, in_hand=(0, 2))
        probs = bot.action_probs(o)
        assert probs.get(Action("call"), 0.0) == pytest.approx(sol.call[2, 0, HAND_CLASSES.index(cls)])


def _direct_evaluation(spot):
    """Equilibrium EVs computed straight from icm_reference.solve, independent of the bot's cache."""
    sol = solve(spot, "icm", tol=rb.SOLVE_TOL, max_iter=rb.SOLVE_MAX_ITER)
    return _Tree(spot, _value_fn(spot, "icm", 0, rb.SOLVE_TOL, rb.SOLVE_MAX_ITER)).evaluate(sol.strategy)


def test_action_values_match_icm_reference_push_and_call_evs():
    payouts = (0.5, 0.3, 0.2)
    spot = Spot((200, 200, 200), 10, 20, payouts)
    ev = _direct_evaluation(spot)
    bot = ReferenceBot(np.random.default_rng(0), payouts)
    for hole, cls in ((("Ah", "Ad"), "AA"), (("7c", "2d"), "72o"), (("Ts", "9s"), "T9s")):
        push, fold = ev.push_ev[0]
        got = bot.action_values(_short_first_in(hole))
        assert set(got) == {Action("raise", 1000), Action("fold")}
        assert abs(got[Action("raise", 1000)] - push[HAND_CLASSES.index(cls)] / spot.prize_pool) < 1e-9
        assert abs(got[Action("fold")] - fold / spot.prize_pool) < 1e-9
    stacks, hist = {0: 0, 1: 950, 2: 900}, ((0, "cbr", 1000), (1, "f", 0))
    call, fold, _ = ev.call_ev[2, 0]
    for hole, cls in ((("Kh", "Kd"), "KK"), (("8c", "3d"), "83o")):
        o = _obs(stacks, {0: 1000, 1: 50, 2: 100}, 2, button=0, hole=hole, history=hist, in_hand=(0, 2))
        got = bot.action_values(o)
        assert set(got) == {Action("call"), Action("fold")}
        assert abs(got[Action("call")] - call[HAND_CLASSES.index(cls)] / spot.prize_pool) < 1e-9
        assert abs(got[Action("fold")] - fold / spot.prize_pool) < 1e-9


def test_action_values_agree_with_action_probs_and_are_none_off_the_reference():
    payouts = (0.5, 0.3, 0.2)
    bot = ReferenceBot(np.random.default_rng(0), payouts)
    for cls in HAND_CLASSES[::7]:
        o = _short_first_in(_cards_of(cls))
        vals, probs = bot.action_values(o), bot.action_probs(o)
        jam, fold = Action("raise", 1000), Action("fold")
        if vals[jam] != vals[fold]:  # pure best response: the higher-EV action is always taken
            assert probs == {max((jam, fold), key=vals.get): 1.0}
    deep = _obs({s: 5000 for s in range(3)}, {0: 0, 1: 50, 2: 100}, 0, button=0, hole=("As", "Kd"))
    assert bot.action_values(deep) is None
    post = _obs({0: 900, 1: 900}, {0: 0, 1: 0}, 0, button=0, hole=("As", "Kd"), board=("2c", "7d", "Jh"))
    assert bot.action_values(post) is None


def test_pure_ranges_lose_almost_nothing_against_the_equilibrium():
    # The bot's range is a best response to the solved profile, so its loss vs the best response is ~0
    # and it is never worse than the averaged fictitious-play strategy.
    spot = Spot((200, 160, 240, 180), 10, 20, (0.5, 0.3, 0.2))
    sol = solve(spot, "icm", tol=rb.SOLVE_TOL, max_iter=rb.SOLVE_MAX_ITER)
    br = solve_ranges(spot, "icm")
    for hero in range(spot.n - 1):
        r = evaluate_spot(lambda s, h, p: br.push[h] if p is None else br.call[h, p], spot, sol, hero)
        assert r["loss"] <= 1e-9 * spot.prize_pool
        assert set(np.unique(br.push[hero])) <= {0.0, 1.0}


def _cards_of(cls):
    a, b = cls[0], cls[1]
    if len(cls) == 2:
        return (a + "h", b + "d")
    return (a + "h", b + ("h" if cls[2] == "s" else "d"))


def test_icm_payouts_change_the_short_stack_decision():
    # The payout structure must reach the decision (flat ICM is tighter than WTA); chip EV off the final table.
    flat_p, wta_p = (0.34, 0.33, 0.33), (1.0,)
    flat = solve_ranges(Spot((200, 200, 200), 10, 20, flat_p), "icm").push[0]
    wta = solve_ranges(Spot((200, 200, 200), 10, 20, wta_p), "icm").push[0]
    cls = HAND_CLASSES[int(np.argmax(np.abs(flat - wta)))]
    assert flat[HAND_CLASSES.index(cls)] != wta[HAND_CLASSES.index(cls)]
    o = _short_first_in(_cards_of(cls))
    for payouts, ref in ((flat_p, flat), (wta_p, wta)):
        got = ReferenceBot(np.random.default_rng(0), payouts).action_probs(o).get(Action("raise", 1000), 0.0)
        assert got == pytest.approx(ref[HAND_CLASSES.index(cls)])
    multi = _obs(o.stacks, o.bets, 0, button=0, hole=o.hole_cards, players_remaining=30)
    p = solve_ranges(Spot((200, 200, 200), 10, 20), "chipev").push[0, HAND_CLASSES.index(cls)]
    assert ReferenceBot(np.random.default_rng(0), flat_p).action_probs(multi).get(
        Action("raise", 1000), 0.0) == pytest.approx(p)


def test_deep_stacks_use_the_chart():
    bot = ReferenceBot(np.random.default_rng(0))
    stacks = {s: 5000 for s in range(6)}
    stacks[2], stacks[3] = 4950, 4900
    bets = {s: 0 for s in range(6)}
    bets[2], bets[3] = 50, 100
    utg = 4  # button 1 -> SB 2, BB 3, UTG 4 with 5 players behind
    open_to = int(100 * load_chart()["open_size_bb"])
    assert bot.action_probs(_obs(stacks, bets, utg, 1, ("As", "Ks"))) == {Action("raise", open_to): 1.0}
    assert bot.action_probs(_obs(stacks, bets, utg, 1, ("7c", "2d"))) == {Action("fold"): 1.0}
    # BB in a limped pot with trash checks; facing a 3bet+ with AA jams.
    limp = ((4, "cc", 100), (5, "f", 0), (0, "f", 0), (1, "f", 0), (2, "cc", 100))
    bets_l = {**bets, 4: 100, 2: 100}
    st_l = {**stacks, 4: 4900, 2: 4900}
    assert bot.action_probs(_obs(st_l, bets_l, 3, 1, ("7c", "2d"), history=limp)) == {Action("call"): 1.0}
    three = ((4, "cbr", 250), (5, "cbr", 750))
    bets_3 = {**bets, 4: 250, 5: 750}
    st_3 = {**stacks, 4: 4750, 5: 4250}
    assert bot.action_probs(_obs(st_3, bets_3, 0, 1, ("Ah", "Ad"), history=three)) == {Action("raise", 5000): 1.0}


def test_postflop_rules_follow_equity_and_pot_odds():
    bot = ReferenceBot(np.random.default_rng(0))
    stacks = {0: 4000, 1: 4000}
    board = ("Ah", "Kh", "7d")
    # Unbet: set of aces bets 2/3 pot, air checks.
    o = _obs(stacks, {0: 0, 1: 0}, 0, 0, ("Ac", "Ad"), board=board, dead=600)
    assert bot.action_probs(o) == {Action("raise", 400): 1.0}
    assert bot.action_probs(_obs(stacks, {0: 0, 1: 0}, 0, 0, ("3c", "2s"), board=board, dead=600)) == {
        Action("call"): 1.0}
    # Facing a pot-size bet: air folds, top set raises.
    st = {0: 4000, 1: 3400}
    assert bot.action_probs(_obs(st, {0: 0, 1: 600}, 0, 0, ("3c", "2s"), board=board, dead=600)) == {
        Action("fold"): 1.0}
    (a, p), = bot.action_probs(_obs(st, {0: 0, 1: 600}, 0, 0, ("Ac", "Ad"), board=board, dead=600)).items()
    assert a.kind == "raise" and p == 1.0


def _sample_observations(n_games=3):
    seen = []

    class Rec(ReferenceBot):
        def act(self, observation):
            seen.append(observation)
            return super().act(observation)

    cfg = load_preset("6max_sng_topheavy")
    for g in range(n_games):
        agents = [Rec(np.random.default_rng([g, p]), cfg.payout_ratios()) if p % 2 else
                  RandomLegalAgent(np.random.default_rng([g, p])) for p in range(cfg.players)]
        res = run_game(cfg, agents, np.random.default_rng(g))
        assert res.illegal_actions == 0
    return seen


def test_decision_function_is_deterministic_and_legal():
    obs = _sample_observations()
    assert len(obs) > 50
    first = [ReferenceBot(np.random.default_rng(1)).action_probs(o) for o in obs]
    rb._solve_spot.cache_clear()
    rb._postflop_equity.cache_clear()
    again = [ReferenceBot(np.random.default_rng(2)).action_probs(o) for o in obs]
    assert first == again
    for o, probs in zip(obs, first):
        assert sum(probs.values()) == pytest.approx(1.0)
        la = o.legal
        for a in probs:
            if a.kind == "raise":
                assert la.min_raise_to is not None and la.min_raise_to <= a.amount <= la.max_raise_to
            if a.kind == "fold":
                assert la.can_fold and la.call_amount > 0


def test_mean_decision_time_is_reported(capsys):
    # Reference measurement only (local, not a CI performance figure).
    obs = _sample_observations(2)
    rb._solve_spot.cache_clear()
    rb._postflop_equity.cache_clear()
    bot = ReferenceBot(np.random.default_rng(0), load_preset("6max_sng_topheavy").payout_ratios())
    t = time.perf_counter()
    for o in obs:
        bot.action_probs(o)
    ms = 1000 * (time.perf_counter() - t) / len(obs)
    with capsys.disabled():
        print(f"\nreference bot: {ms:.2f} ms/decision over {len(obs)} decisions (cold caches)")
    assert ms < 1000


@pytest.mark.slow
@pytest.mark.parametrize("preset", ["6max_sng_wta", "9max_sng_503020"])
def test_reference_bot_beats_random_bot_over_200_tournaments(preset):
    cfg = load_preset(preset)
    res = evaluate(cfg, factory(cfg.payout_ratios()), lambda rng: RandomLegalAgent(rng), blocks=100, seed=15,
                   candidate_name="reference_bot_v1", baseline_name="random_legal",
                   reference_version=REFERENCE_BOT_VERSION)
    assert res.games == 200 and res.illegal_actions == 0
    assert res.ci.lo > 0, res.to_json()
