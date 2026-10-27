import numpy as np
import pytest

from referee.gate_r.cash import (
    CASH_ITEMS,
    CashRules,
    check_cash_session,
    tally_for_cash,
)
from stalker.agents.base import Action, Agent
from stalker.agents.random_agent import RandomLegalAgent
from stalker.cash.presets import PRESETS, preset
from stalker.cash.session import CashConfig, bb_per_100, run_cash_session


def _run(cfg, seed, engine="fast"):
    ss = np.random.SeedSequence(seed).spawn(cfg.seats + 1)
    agents = [RandomLegalAgent(np.random.default_rng(s)) for s in ss[1:]]
    return run_cash_session(cfg, agents, np.random.default_rng(ss[0]), engine=engine)


def _gate_r(cfg, result):
    lo, hi = cfg.buy_range
    rules = CashRules(seats=cfg.seats, sb=cfg.sb, bb=cfg.bb, min_buyin=lo, max_buyin=hi, hands=cfg.hands)
    tally = tally_for_cash()
    check_cash_session(rules, list(result.events), tally, where=cfg.name)
    return tally


def test_presets_are_fixed():
    want = {f"cash_{t}_{d}bb": (n, d) for t, n in (("hu", 2), ("6max", 6), ("9max", 9)) for d in (40, 100, 200)}
    assert {name: (c.seats, c.depth_bb) for name, c in PRESETS.items()} == want
    for name, c in PRESETS.items():
        assert (c.name, c.sb, c.bb, c.hands, c.auto_topup) == (name, 1, 2, 1000, False)
        assert c.buy_range == (c.buyin, c.buyin)


@pytest.mark.parametrize("name", sorted(PRESETS))
@pytest.mark.parametrize("auto_topup", [False, True])
def test_preset_1000_hands_pass_gate_r_cash_checks(name, auto_topup):
    cfg = preset(name, auto_topup=auto_topup)
    res = _run(cfg, seed=sum(map(ord, name)) + auto_topup)
    tally = _gate_r(cfg, res)
    assert tally.failures == [], tally.failures[:5]
    counts = tally.counts
    assert all(counts[k][1] > 0 for k in CASH_ITEMS if k != "cash_topup"), counts
    assert sum(1 for e in res.events if e["type"] == "HAND") == 1000
    assert sum(1 for e in res.events if e["type"] == "REBUY") > 0  # random agents bust; re-buys are exercised
    if auto_topup:
        assert counts["cash_topup"][1] > 0
        assert sum(res.topups) > 0
    else:
        assert not any(e["type"] == "TOPUP" for e in res.events)


def test_net_sums_to_zero_and_matches_stream():
    cfg = preset("cash_6max_100bb", hands=300, auto_topup=True)
    res = _run(cfg, seed=7)
    assert sum(res.net) == 0
    bought = [0] * cfg.seats
    for e in res.events:
        if e["type"] in ("SEAT", "REBUY", "TOPUP"):
            bought[e["seat"]] += e["amount"]
    final = res.events[-1]["stacks"]
    assert res.net == tuple(final[s] - bought[s] for s in range(cfg.seats))
    assert res.bb_per_100() == tuple(n / cfg.bb / cfg.hands * 100 for n in res.net)


def test_bb_per_100():
    assert bb_per_100(400, 100, 2) == 200.0  # +200 bb over 100 hands
    assert bb_per_100(-30, 1000, 2) == -1.5
    with pytest.raises(ValueError):
        bb_per_100(10, 0, 2)


def test_same_seed_same_stream():
    cfg = preset("cash_9max_40bb", hands=200)
    a, b = _run(cfg, seed=3), _run(cfg, seed=3)
    assert a.events == b.events and a.net == b.net
    assert _run(cfg, seed=4).events != a.events


def test_fast_and_pokerkit_engines_give_the_same_stream():
    cfg = preset("cash_6max_40bb", hands=60, auto_topup=True)
    assert _run(cfg, seed=11).events == _run(cfg, seed=11, engine="pokerkit").events


class _Shover(Agent):
    def act(self, obs):
        la = obs.legal
        return Action("raise", la.max_raise_to) if la.min_raise_to is not None else Action("call")


def test_busted_seat_rebuys_before_next_hand_and_button_moves():
    cfg = CashConfig("t", 2, 1, 2, 80, hands=4)
    res = run_cash_session(cfg, [_Shover(), _Shover()], np.random.default_rng(5))
    ev = list(res.events)
    hands = [e for e in ev if e["type"] == "HAND"]
    assert [h["button"] for h in hands[1:]] == [(hands[0]["button"] + k) % 2 for k in (1, 2, 3)]
    assert all(min(h["stacks"].values()) > 0 for h in hands)
    for i, e in enumerate(ev):  # every all-in either busts someone (re-buy follows) or chops
        if e["type"] == "HAND_END" and 0 in e["stacks"].values() and i + 1 < len(ev):
            assert ev[i + 1]["type"] == "REBUY" and ev[i + 1]["amount"] == 80 and ev[i + 1]["stack"] == 0
    assert sum(res.net) == 0 and res.rebuys == tuple(
        sum(e["amount"] for e in ev if e["type"] == "REBUY" and e["seat"] == s) for s in range(2))


def test_config_validation():
    with pytest.raises(ValueError, match="seats"):
        CashConfig("t", 10, 1, 2, 200, 10)
    with pytest.raises(ValueError, match="buyin"):
        CashConfig("t", 2, 1, 2, 200, 10, min_buyin=300)
    with pytest.raises(ValueError, match="agents"):
        run_cash_session(PRESETS["cash_hu_100bb"], [_Shover()], np.random.default_rng(0))
    with pytest.raises(KeyError, match="cash_hu_100bb"):
        preset("cash_hu_50bb")
