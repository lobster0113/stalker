import copy

import pytest

from referee.gate_r.cash import CASH_ITEMS, CashRules, check_cash_session, tally_for_cash

RULES = CashRules(seats=3, sb=1, bb=2, min_buyin=100, max_buyin=200, hands=3)


def good():
    return [
        {"type": "SEAT", "seat": 0, "amount": 200},
        {"type": "SEAT", "seat": 1, "amount": 150},
        {"type": "SEAT", "seat": 2, "amount": 100},
        {"type": "HAND", "button": 0, "stacks": {0: 200, 1: 150, 2: 100}},
        {"type": "HAND_END", "stacks": {0: 100, 1: 250, 2: 100}},
        {"type": "TOPUP", "seat": 0, "amount": 100, "stack": 100},
        {"type": "HAND", "button": 1, "stacks": {0: 200, 1: 250, 2: 100}},
        {"type": "HAND_END", "stacks": {0: 250, 1: 300, 2: 0}},
        {"type": "REBUY", "seat": 2, "amount": 100, "stack": 0},
        {"type": "HAND", "button": 2, "stacks": {0: 250, 1: 300, 2: 100}},
        {"type": "HAND_END", "stacks": {0: 250, 1: 300, 2: 100}},
    ]


def run(events, rules=RULES):
    t = tally_for_cash()
    check_cash_session(rules, events, t)
    return t


def failed(t):
    return {k for k, (p, n) in t.counts.items() if p != n}


def test_good_stream_passes_all_five_items():
    t = run(good())
    assert tuple(t.counts) == CASH_ITEMS
    assert failed(t) == set() and all(n > 0 for _, n in t.counts.values()), t.failures


def _mut(fn):
    ev = copy.deepcopy(good())
    fn(ev)
    return ev


def _topup_over_cap(e):  # 100 + 150 > max buy-in; later stacks follow so only the cap rule is broken
    e[5]["amount"] = 150
    e[6]["stacks"][0] = 250
    e[7]["stacks"] = {0: 250, 1: 350, 2: 0}
    e[9]["stacks"] = {0: 250, 1: 350, 2: 100}
    e[10]["stacks"] = {0: 250, 1: 350, 2: 100}


def _button_skips_seat(e):
    e[6]["button"] = 2
    e[9]["button"] = 0


VIOLATIONS = {
    "cash_rebuy": lambda e: e[8].update(stack=5),                    # re-buy with chips left
    "cash_topup": _topup_over_cap,
    "button": _button_skips_seat,
    "chip_conservation": lambda e: e[4]["stacks"].update({1: 300}),  # chips appear from nowhere
    "session_length": lambda e: e.__delitem__(slice(8, 11)),         # one hand short
}


@pytest.mark.parametrize("item", CASH_ITEMS)
def test_each_violation_fails_exactly_its_item(item):
    t = run(_mut(VIOLATIONS[item]))
    assert failed(t) == {item}, (t.failures, failed(t))


def test_topup_during_a_hand_fails():
    ev = good()
    ev.insert(4, {"type": "TOPUP", "seat": 1, "amount": 50, "stack": 150})
    assert "cash_topup" in failed(run(ev))
