"""short_stack_rule='skip' (#185): hand-computed postings, a full game, and the Gate R check that catches 'all_in'."""
import dataclasses

import numpy as np
import pytest

from referee.gate_r.checks import check_game
from referee.gate_r.suite import CallingStation, variants
from stalker.agents.base import Action, Agent
from stalker.tournament.config import BlindLevel, TournamentConfig, load_preset
from stalker.tournament.director import _Game, run_game
from stalker.tournament.hand import Hand


class Folder(Agent):
    def act(self, obs):
        return Action("fold" if obs.legal.can_fold and obs.legal.call_amount > 0 else "call")


def _table_game(stacks: dict[int, int], level: BlindLevel, ante_mode="none"):
    """One 9-seat table with player p in seat p, about to deal with the button on seat 0."""
    cfg = TournamentConfig(name="t", players=len(stacks), table_size=9, starting_stack=1000, levels=(level,),
                           payouts=(1.0,), ante_mode=ante_mode, short_stack_rule="skip")
    events = []
    g = _Game(cfg, [Folder() for _ in stacks], np.random.default_rng(0), events.append, "g", "t")
    (table,) = g.tables.values()
    table.seats = [p if p in stacks else None for p in range(9)]
    table.button = max(stacks)  # next_button() moves it to the lowest occupied seat, 0
    g.stacks = dict(stacks)
    return g, table, events


def _hands(events):
    """(NEW_HAND data, first ACTION data, HAND_END final stacks) per hand."""
    out, cur = [], None
    for e in events:
        if e.type == "NEW_HAND":
            cur = [e.data, None, None]
        elif e.type == "ACTION" and cur[1] is None:
            cur[1] = e.data
        elif e.type == "HAND_END":
            cur[2] = e.data["final_stacks"]
            out.append(tuple(cur))
    return out


def test_short_bb_seat_is_skipped_and_the_blinds_move_on():
    stacks = {s: 1000 for s in range(9)}
    stacks[2] = 60  # 60 < bb 100
    g, table, events = _table_game(stacks, BlindLevel(50, 100, 0, 10))
    g._play_hand(table, 1)
    g._play_hand(table, 2)
    (d1, a1, f1), (d2, a2, f2) = _hands(events)
    # hand 1: button 0; clockwise 1, 2, 3, ... Seat 2 cannot cover 100 -> SB 1, BB 3, seat 4 opens.
    assert d1["button"] == 0 and d1["blind_seats"] == (1, 3) and a1["seat"] == 4
    # all fold to BB 3: it wins the SB's 50; seat 2 (dealt in, no blind) keeps 60.
    assert (f1[1], f1[2], f1[3]) == (950, 60, 1050)
    # hand 2: button to seat 1 (next occupied, no dead button); seat 2 still short -> SB 3, BB 4, seat 5 opens.
    assert d2["button"] == 1 and d2["blind_seats"] == (3, 4) and a2["seat"] == 5
    assert (f2[2], f2[3], f2[4]) == (60, 1000, 1050)


def test_classic_ante_counts_toward_the_skip_threshold():
    stacks = {s: 1000 for s in range(9)}
    stacks[1] = 105  # covers bb 100 but not bb + ante 110
    g, table, events = _table_game(stacks, BlindLevel(50, 100, 10, 10), ante_mode="classic")
    g._play_hand(table, 1)
    ((d, a, f),) = _hands(events)
    # button 0; seat 1 skipped (still antes 10) -> SB 2, BB 3, seat 4 opens.
    assert d["blind_seats"] == (2, 3) and a["seat"] == 4
    # pot = 9 antes x 10 + 50 + 100 = 240 to BB 3: 1000 - 10 - 100 + 240 = 1130; SB 2: 1000 - 10 - 50 = 940.
    assert (f[1], f[2], f[3], f[0]) == (95, 940, 1130, 990)
    assert sum(f.values()) == sum(stacks.values())


def test_fewer_than_two_covering_seats_falls_back_to_all_in_postings():
    g, table, events = _table_game({0: 1000, 1: 30, 2: 40}, BlindLevel(50, 100, 0, 10))
    g._play_hand(table, 1)
    ((d, _, f),) = _hands(events)
    # only seat 0 covers 100 -> usual postings: SB 1 all-in for 30, BB 2 all-in for 40.
    assert d["blind_seats"] == (1, 2)
    assert sum(f.values()) == 1070


def test_hand_rejects_bad_blind_seats():
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="blind_seats"):
        Hand([100, 100, 100], 0, 1, 2, rng, blind_seats=(2, 1))  # BB before SB
    with pytest.raises(ValueError, match="blind_seats"):
        Hand([100, 100], 0, 1, 2, rng, blind_seats=(0, 1))  # heads-up keeps the button-SB rule


def _skip_game(seed):
    _, cfg = list(variants("9max_sng_skip"))[1]  # 2-hand levels: antes and short stacks early
    events = []
    res = run_game(cfg, [CallingStation(np.random.default_rng([seed, i])) for i in range(cfg.players)],
                   np.random.default_rng(seed), observer=events.append)
    return cfg, events, res


def _skipped(d):
    """True when the recorded blinds differ from the plain first-two-seats placement."""
    occ = sorted(d["seat_players"], key=lambda s: (s - d["button"] - 1) % 9)
    return len(occ) > 2 and tuple(d["blind_seats"]) != tuple(occ[:2])


def test_skip_game_runs_to_the_end_and_passes_gate_r(monkeypatch):
    cfg, events, res = _skip_game(0)
    assert sorted(res.ranks) == list(range(1, cfg.players + 1))
    assert any(_skipped(e.data) for e in events if e.type == "NEW_HAND")
    t = check_game(cfg, events, res)
    assert t.failures == [] and t.passed == t.total

    # a director that ignores the rule (all_in postings under a 'skip' config) must fail antes_blinds
    monkeypatch.setattr(_Game, "_blind_seats", lambda *a: None)
    cfg, events, res = _skip_game(0)
    passed, total = check_game(cfg, events, res).counts["antes_blinds"]
    assert passed < total


def test_gate_r_rejects_wrong_recorded_blind_seats():
    cfg = load_preset("6max_sng_wta")
    events = []
    res = run_game(cfg, [CallingStation(np.random.default_rng([0, i])) for i in range(cfg.players)],
                   np.random.default_rng(0), observer=events.append)
    i = next(k for k, e in enumerate(events) if e.type == "NEW_HAND")
    sb, bb = events[i].data["blind_seats"]
    events[i] = dataclasses.replace(events[i], data={**events[i].data, "blind_seats": (bb, sb)})
    passed, total = check_game(cfg, events, res).counts["antes_blinds"]
    assert passed == total - 1
