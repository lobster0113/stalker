import dataclasses

import numpy as np
import pytest

from referee.gate_r import __main__ as cli
from referee.gate_r.checks import ITEMS, Tally, check_game
from referee.gate_r.evaluator import strength
from referee.gate_r.settlement import settle
from referee.gate_r.suite import SLOW_PRESETS, CallingStation, run_suite, variants
from stalker.agents.random_agent import RandomLegalAgent
from stalker.core.cards import card_str
from stalker.core.evaluator import evaluate
from stalker.tournament.config import load_preset, preset_names
from stalker.tournament.director import run_game

# ---- independent settlement: hand-computed cases ----
# (paid, folded, strength, order, antes, expected winnings)
SETTLE_CASES = {
    "three_allins_short_wins_main": (
        {0: 100, 1: 300, 2: 300}, set(), {0: 3, 1: 2, 2: 1}, [0, 1, 2], None, {0: 300, 1: 400, 2: 0}),
    "three_allins_big_wins_all": (
        {0: 100, 1: 300, 2: 300}, set(), {0: 1, 1: 2, 2: 3}, [0, 1, 2], None, {0: 0, 1: 0, 2: 700}),
    "middle_wins_main_and_side": (
        {0: 100, 1: 300, 2: 300}, set(), {0: 2, 1: 3, 2: 1}, [0, 1, 2], None, {0: 0, 1: 700, 2: 0}),
    "tie_on_main_side_to_other": (  # B cannot win anything and is mucked; A and C split the main
        {0: 100, 1: 300, 2: 300}, set(), {0: 5, 1: 1, 2: 5}, [0, 1, 2], None, {0: 150, 1: 0, 2: 550}),
    "odd_chip_first_left_of_button": (  # button 0: order 1, 2, 0
        {0: 50, 1: 50, 2: 1}, {2}, {0: 4, 1: 4}, [1, 2, 0], None, {0: 50, 1: 51, 2: 0}),
    "three_way_tie_all_odd_chips_to_first": (
        {0: 34, 1: 34, 2: 34, 3: 2}, {3}, {0: 7, 1: 7, 2: 7}, [3, 0, 1, 2], None, {0: 36, 1: 34, 2: 34, 3: 0}),
    "bb_ante_is_dead_money_in_lowest_pot": (  # B posted ante 50; A all-in for 20 still wins every ante chip
        {0: 20, 1: 150, 2: 100}, set(), {0: 9, 1: 1, 2: 5}, [0, 1, 2], {1: 50}, {0: 110, 1: 0, 2: 160}),
    "all_in_from_ante_wins_ante_pot_only": (
        {0: 10, 1: 110, 2: 110}, set(), {0: 9, 1: 5, 2: 1}, [0, 1, 2], {0: 10, 1: 10, 2: 10},
        {0: 30, 1: 200, 2: 0}),
    "folded_chips_feed_pots_they_reached": (
        {0: 200, 1: 50, 2: 200}, {0}, {1: 9, 2: 1}, [0, 1, 2], None, {0: 0, 1: 150, 2: 300}),
    "mucked_loser_merges_pots_before_odd_chip_split": (  # unmerged split would give 88/86
        {0: 33, 1: 50, 2: 50, 3: 40, 4: 1}, {3, 4}, {0: 1, 1: 8, 2: 8}, [1, 2, 0, 3, 4], None,
        {0: 0, 1: 87, 2: 87, 3: 0, 4: 0}),
    "uncontested_takes_everything": (
        {0: 25, 1: 50, 2: 0}, {0, 2}, {}, [0, 1, 2], None, {0: 0, 1: 75, 2: 0}),
}


@pytest.mark.parametrize("name", list(SETTLE_CASES))
def test_settle_hand_computed(name):
    paid, folded, keys, order, antes, want = SETTLE_CASES[name]
    got = settle(paid, folded, keys, order, antes)
    assert got == want
    assert sum(got.values()) == sum(paid.values())


def test_settle_rejects_chips_only_folded_seats_reached():
    with pytest.raises(ValueError, match="refund uncalled"):
        settle({0: 300, 1: 50, 2: 100}, {0}, {1: 1, 2: 2}, [0, 1, 2])


# ---- independent evaluator ----
def test_evaluator_category_order():
    board = ["2c", "7d", "9h", "Jc", "Ks"]
    ladder = [
        (["3d", "4s"], board),                      # high card
        (["2d", "4s"], board),                      # pair
        (["2d", "7s"], board),                      # two pair
        (["2d", "2s"], board),                      # trips
        (["Ts", "Qd"], board),                      # straight
        (["Ac", "3c"], ["2c", "7c", "9h", "Jc", "Ks"]),  # flush
        (["2d", "2s"], ["2c", "7d", "7h", "Jc", "Ks"]),  # full house
        (["7s", "7c"], ["2c", "7d", "7h", "Jc", "Ks"]),  # quads
        (["Tc", "Qc"], ["9c", "Jc", "Kc", "2d", "3h"]),  # straight flush
    ]
    keys = [strength(h, b) for h, b in ladder]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    assert strength(["Ad", "2s"], ["3c", "4d", "5h", "9c", "Ks"]) < strength(["6d", "2s"], ["3c", "4d", "5h", "9c", "Ks"])


def test_evaluator_agrees_with_product_evaluator_on_random_pairs():
    rng = np.random.default_rng(7)
    for _ in range(400):
        deck = rng.permutation(52)
        board, h1, h2 = deck[:5], deck[5:7], deck[7:9]
        k1, k2 = strength(*_s(h1, board)), strength(*_s(h2, board))
        e1, e2 = evaluate([*h1, *board]), evaluate([*h2, *board])
        assert (k1 > k2) - (k1 < k2) == (e1 > e2) - (e1 < e2)


def _s(hole, board):
    return [card_str(int(c)) for c in hole], [card_str(int(c)) for c in board]


# ---- the replay checks catch broken engines ----
def _game(preset="6max_sng_wta", seed=0):
    cfg = load_preset(preset)
    events = []
    res = run_game(cfg, [RandomLegalAgent(np.random.default_rng([seed, i])) for i in range(cfg.players)],
                   np.random.default_rng(seed), observer=events.append)
    return cfg, events, res


def _replace(e, **data):
    return dataclasses.replace(e, data={**e.data, **data})


def test_clean_game_passes_every_item():
    cfg, events, res = _game()
    t = check_game(cfg, events, res)
    assert t.passed == t.total and t.failures == []
    assert all(total > 0 for _, total in t.counts.values())


def _first(events, typ, pred=lambda e: True):
    return next(i for i, e in enumerate(events) if e.type == typ and pred(e))


def _fails(cfg, events, res, item):
    t = check_game(cfg, events, res)
    passed, total = t.counts[item]
    return passed < total


def test_detects_wrong_settlement_even_when_chips_conserved():
    cfg, events, res = _game()
    i = _first(events, "HAND_END", lambda e: any(v != 0 for v in e.data["deltas"].values()))
    fs, dl = dict(events[i].data["final_stacks"]), dict(events[i].data["deltas"])
    a, b = sorted(fs, key=lambda s: -fs[s])[:2]
    fs[a] -= 1; fs[b] += 1; dl[a] -= 1; dl[b] += 1  # noqa: E702
    events[i] = _replace(events[i], final_stacks=fs, deltas=dl)
    assert _fails(cfg, events, res, "settlement")


def test_detects_chip_creation():
    cfg, events, res = _game()
    i = _first(events, "HAND_END")
    fs, dl = dict(events[i].data["final_stacks"]), dict(events[i].data["deltas"])
    s = next(iter(fs))
    fs[s] += 5; dl[s] += 5  # noqa: E702
    events[i] = _replace(events[i], final_stacks=fs, deltas=dl)
    assert _fails(cfg, events, res, "chip_conservation")


def test_detects_wrong_blind_level():
    cfg, events, res = _game()
    i = _first(events, "NEW_HAND")
    events[i] = _replace(events[i], bb=events[i].data["bb"] * 2)
    assert _fails(cfg, events, res, "antes_blinds")


def test_detects_out_of_turn_action():
    cfg, events, res = _game()
    i = _first(events, "ACTION")
    seats = list(events[_first(events, "NEW_HAND")].data["seat_players"])
    wrong = next(s for s in seats if s != events[i].data["seat"])
    events[i] = _replace(events[i], seat=wrong)
    assert _fails(cfg, events, res, "action_order")


def test_detects_wrong_call_amount_and_undersized_raise():
    cfg, events, res = _game()
    i = _first(events, "ACTION", lambda e: e.data["action"] == "call" and e.data["amount"] > 0)
    events[i] = _replace(events[i], amount=events[i].data["amount"] + 1)
    assert _fails(cfg, events, res, "bet_sizing")
    cfg, events, res = _game()
    bb = events[_first(events, "NEW_HAND")].data["bb"]
    i = _first(events, "ACTION", lambda e: e.data["action"] == "raise" and e.data["street"] == 0)
    events[i] = _replace(events[i], amount=bb + 1)  # below a min raise to 2 BB, and not an all-in
    assert _fails(cfg, events, res, "bet_sizing")


def test_heads_up_button_must_post_small_blind_and_act_first():
    cfg, events, res = _game()
    i = _first(events, "NEW_HAND", lambda e: len(e.data["seat_players"]) == 2)
    j = _first(events, "ACTION", lambda e: e.hand_id == events[i].hand_id)
    assert events[j].data["seat"] == events[i].data["button"]
    assert check_game(cfg, events, res).passed == check_game(cfg, events, res).total


def test_detects_showdown_of_folded_seat():
    for seed in range(50):
        cfg, events, res = _game(seed=seed)
        folds = {(e.hand_id, e.data["seat"]) for e in events if e.type == "ACTION" and e.data["action"] == "fold"}
        i = next((i for i, e in enumerate(events) if e.type == "SHOWDOWN"
                  and any(h == e.hand_id for h, _ in folds)), None)
        if i is not None:
            break
    folded = next(s for h, s in folds if h == events[i].hand_id)
    events[i] = _replace(events[i], hands={**events[i].data["hands"], folded: ("2c", "2d")})
    assert _fails(cfg, events, res, "street_flow")


def test_detects_button_skip_and_rank_errors():
    cfg, events, res = _game()
    idx = [i for i, e in enumerate(events) if e.type == "NEW_HAND"]
    i = idx[1]
    occ = sorted(events[i].data["seat_players"])
    wrong = next(s for s in occ if s != events[i].data["button"])
    events[i] = _replace(events[i], button=wrong)
    assert _fails(cfg, events, res, "button")
    cfg, events, res = _game()
    ranks = list(res.ranks)
    a, b = ranks.index(1), ranks.index(2)
    ranks[a], ranks[b] = 2, 1
    assert _fails(cfg, events, dataclasses.replace(res, ranks=tuple(ranks)), "elimination")
    prizes = list(res.prizes)
    prizes[a] += 1
    assert _fails(cfg, events, dataclasses.replace(res, prizes=tuple(prizes)), "prizes")


def test_tally_merge_and_rate():
    a, b = Tally(), Tally()
    a.check("button", True)
    b.check("button", False, "x")
    a.merge(b)
    assert a.counts["button"] == [1, 2] and a.pass_rate == 0.5 and a.failures == ["button: x"]
    assert set(a.counts) == set(ITEMS)


# ---- the suite over every preset ----
# mtt54 is multi-second too; the quick gate keeps the small presets (#104).
_PRESETS = [pytest.param(p, marks=pytest.mark.slow) if p in SLOW_PRESETS or p == "mtt54" else p
            for p in preset_names()]


@pytest.mark.parametrize("preset", _PRESETS)
def test_gate_r_suite_every_preset(preset):
    t = run_suite(seeds=1 if preset in SLOW_PRESETS else 2, presets=[preset])
    assert t.failures == [], "\n".join(t.failures)
    assert t.passed == t.total
    for item in ("settlement", "action_order", "bet_sizing", "antes_blinds"):
        assert t.counts[item][1] > 0


def test_fast_variant_reaches_antes_and_short_stack_postings():
    _, cfg = list(variants("mtt54"))[1]
    events = []
    run_game(cfg, [CallingStation(np.random.default_rng([0, i])) for i in range(cfg.players)],
             np.random.default_rng(0), observer=events.append)
    ante_hands = [e.data for e in events if e.type == "NEW_HAND" and e.data["ante"]]
    assert ante_hands
    assert any(min(d["stacks"].values()) < d["ante"] + d["bb"] for d in ante_hands)


def test_cli_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_cash_suite", lambda sessions, hands: (Tally(counts={}), 0))
    good = Tally()
    good.check("button", True)
    monkeypatch.setattr(cli, "run_suite", lambda seeds, full: good)
    assert cli.main([]) == 0
    bad = Tally()
    bad.check("settlement", False, "hand 1 off by 1")
    monkeypatch.setattr(cli, "run_suite", lambda seeds, full: bad)
    assert cli.main(["--full"]) == 1
    out = capsys.readouterr().out
    assert "settlement         0/1" in out and "hand 1 off by 1" in out


def test_all_settle_cases_cover_split_and_side_pots():
    assert len(SETTLE_CASES) >= 8
    multi_allin = [n for n, c in SETTLE_CASES.items() if len({v for v in c[0].values() if v}) >= 2]
    assert len(multi_allin) >= 8
    assert any(len([v for v in c[5].values() if v]) >= 2 and len(set(c[2].values())) < len(c[2])
               for c in SETTLE_CASES.values())


def test_referee_side_never_imports_the_engine_it_judges():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "referee" / "gate_r"
    for name in ("settlement.py", "evaluator.py", "checks.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not any(m.startswith(("pokerkit", "stalker")) for m in mods), f"{name} imports {mods}"
