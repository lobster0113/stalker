import dataclasses

import pytest

import referee.gate_r.__main__ as cli
from referee import metrics
from referee.gate_r import cash_suite
from referee.gate_r.cash_suite import ITEMS, run_cash_suite
from referee.gate_r.checks import Tally
from stalker.cash import session
from stalker.cash.presets import PRESETS
from stalker.tournament.fast_hand import FastHand


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_quick_three_way_agreement_per_preset(name):
    # 2 sessions x 50 hands: both bots, with and without auto top-up (the quick gate's share, #147)
    tally, hands = run_cash_suite(sessions=2, hands=50, presets=[name], workers=1)
    assert tally.failures == [], tally.failures[:5]
    assert hands == 100 and tally.passed == tally.total
    assert all(tally.counts[k][1] > 0 for k in ITEMS), tally.counts


def test_full_suite_covers_every_preset_with_100k_hands():
    assert cash_suite.FULL_SESSIONS * cash_suite.FULL_HANDS * len(PRESETS) >= 100_000
    assert {cash_suite._variant(s) for s in range(4)} == {(b, t) for b in ("random", "station") for t in (False, True)}


def _tamper_one_chip(monkeypatch, at_hand=3):
    """FastHand gives one chip of one hand to the next seat; PokerKit stays honest."""
    made = []

    class OffByOne(FastHand):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            made.append(self)

        def result(self):
            res = super().result()
            if len(made) != at_hand:
                return res
            final = list(res.final_stacks)
            src = next(i for i, c in enumerate(final) if c > 0)
            final[src] -= 1
            final[(src + 1) % len(final)] += 1
            return dataclasses.replace(res, final_stacks=tuple(final),
                                       deltas=tuple(f - s for f, s in zip(final, res.starting_stacks)))

    monkeypatch.setitem(session._ENGINES, "fast", OffByOne)


def test_one_chip_from_one_engine_fails_three_way_agreement(monkeypatch):
    _tamper_one_chip(monkeypatch)
    tally = cash_suite.check_session("cash_6max_100bb", 0, 10)
    failed = {k for k, (p, n) in tally.counts.items() if p != n}
    assert {"engine_agreement", "settlement"} <= failed, tally.counts
    assert all("[pokerkit]" not in f for f in tally.failures if f.startswith("settlement")), tally.failures
    assert any("[fast]" in f for f in tally.failures if f.startswith("settlement")), tally.failures


def test_closing_action_pot_is_the_only_ignored_field(monkeypatch):
    # any other per-hand difference, here a non-closing action's pot, breaks agreement
    real = cash_suite._play

    def skew(name, seed, hands, engine):
        cfg, res, events = real(name, seed, hands, engine)
        if engine == "fast":
            i = next(i for i, e in enumerate(events) if e.type == "ACTION" and events[i + 1].type == "ACTION")
            events[i] = dataclasses.replace(events[i], data={**events[i].data, "pot": events[i].data["pot"] + 1})
        return cfg, res, events

    monkeypatch.setattr(cash_suite, "_play", skew)
    tally = cash_suite.check_session("cash_hu_100bb", 1, 5)
    assert tally.counts["engine_agreement"] == [0, 1]


def test_cli_reports_cash_and_fails_on_cash_failure(monkeypatch, capsys):
    good = Tally()
    good.check("button", True)
    monkeypatch.setattr(cli, "run_suite", lambda seeds, full: good)
    seen = []

    def cash(sessions, hands):
        seen.append((sessions, hands))
        t = cash_suite.tally_for_cash(ITEMS)
        t.check("engine_agreement", ok, "fast vs pokerkit: hand 2")
        return t, sessions * hands * len(PRESETS)

    monkeypatch.setattr(cli, "run_cash_suite", cash)
    ok = True
    assert cli.main([]) == 0
    ok = False
    assert cli.main(["--full"]) == 1
    assert seen == [(cash_suite.QUICK_SESSIONS, cash_suite.QUICK_HANDS),
                    (cash_suite.FULL_SESSIONS, cash_suite.FULL_HANDS)]
    out = capsys.readouterr().out
    assert "gate_r_cash (108000 hands x 2 engines)" in out and "fast vs pokerkit: hand 2" in out


def test_metrics_record_cash_keys(monkeypatch):
    t = Tally()
    t.check("button", True)
    c = cash_suite.tally_for_cash(ITEMS)
    c.check("settlement", True)
    c.check("settlement", False, "x")
    monkeypatch.setattr("referee.gate_r.suite.run_suite", lambda: t)
    monkeypatch.setattr(cash_suite, "run_cash_suite", lambda: (c, 0))
    snap = metrics.gate_r()
    assert snap["gate_r_cash_pass_rate"] == 0.5 and snap["gate_r_cash_checks"] == 2
    assert snap["gate_r_pass_rate"] == 1.0
