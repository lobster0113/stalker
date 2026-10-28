import dataclasses
import json
import math

import numpy as np
import pytest

from stalker.agents.base import Action, Agent, Observation
from stalker.records.schema import (
    ActionOption,
    DecisionRecord,
    GameRecord,
    HandRecord,
    MemorySnapshot,
    PlayerHandOutcome,
    PolicySource,
    PublicAction,
    RecordError,
    RecordIds,
    SeatInfo,
    StackSummary,
    TableObservation,
    TournamentContext,
    ensure_valid,
    from_dict,
    to_dict,
    validate,
)
from stalker.records.store import (
    RECORDS,
    RecordWriter,
    RunManifest,
    load_records,
    read_manifest,
    write_manifest,
)
from stalker.tournament.config import load_preset
from stalker.tournament.director import run_game

STREET_BY_BOARD = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}


def _decision(**over) -> DecisionRecord:
    probs = (0.2, 0.5, 0.3, 0.0)
    base = DecisionRecord(
        ids=RecordIds("ep-1", "g-1", "t-1", hand_id=3, decision_id=17, player_id=2, policy_version="v0"),
        tournament_context=TournamentContext(
            table_size=6, sb=50, bb=100, ante_type="bb_ante", ante=100, level=2, remaining=5, paid_places=2,
            payout_vector=(65.0, 35.0), next_level=(75, 150, 150), stacks=StackSummary.of([1500, 2000, 900, 3000, 1600])),
        table_observation=TableObservation(
            seats=(SeatInfo(0, 4, 1500, 0, True), SeatInfo(2, 2, 1900, 100, True), SeatInfo(3, 1, 900, 50, True)),
            hero_seat=2, button=0, position="BB", pot=250, hole_cards=("As", "Kd"), board=(), street="preflop",
            current_hand_actions=(PublicAction(3, "cc", 0),),
            action_space=(ActionOption("fold"), ActionOption("call"), ActionOption("raise", 300),
                          ActionOption("raise", 2000)),
            legal_action_mask=(True, True, True, False)),
        session_memory_snapshot=MemorySnapshot(hands_observed=2, features={"vpip_seat3": 0.5}),
        probs_ai0=probs, probs_ai1=(0.1, 0.6, 0.3, 0.0), acting_policy="ai0", chosen_action=1,
        action_logprob=math.log(0.5), action_values=None, policy_source=PolicySource("unit-test"))
    return dataclasses.replace(base, **over)


def _obs(r: DecisionRecord, **over) -> DecisionRecord:
    return dataclasses.replace(r, table_observation=dataclasses.replace(r.table_observation, **over))


def _hand(**over) -> HandRecord:
    base = HandRecord("ep-1", "g-1", "t-1", hand_id=3, table_id=0, players=(
        PlayerHandOutcome(4, 0, 1500, 1750, 250), PlayerHandOutcome(2, 2, 2000, 1750, -250),
        PlayerHandOutcome(1, 3, 900, 900, 0)), busted=(), terminal_flag=False)
    return dataclasses.replace(base, **over)


def test_ids_are_separate_fields():
    names = {f.name for f in dataclasses.fields(RecordIds)}
    assert names == {"episode_id", "game_id", "tournament_id", "hand_id", "decision_id", "player_id", "policy_version"}


def test_valid_decision_round_trips_through_json():
    r = _decision()
    assert validate(r) == []
    back = from_dict(DecisionRecord, json.loads(json.dumps(to_dict(r))))
    assert back == r


@pytest.mark.parametrize("make, needle", [
    (lambda r: dataclasses.replace(r, probs_ai0=(0.2, 0.5, 0.3, 0.01)), "probs_ai0 sums"),
    (lambda r: dataclasses.replace(r, probs_ai1=(0.1, 0.6, 0.2, 0.0)), "probs_ai1 sums"),
    (lambda r: dataclasses.replace(r, probs_ai0=(-0.1, 0.8, 0.3, 0.0)), ">= 0"),
    (lambda r: dataclasses.replace(r, chosen_action=3, action_logprob=0.0), "not legal"),
    (lambda r: dataclasses.replace(r, chosen_action=7), "must index"),
    (lambda r: dataclasses.replace(r, action_logprob=math.log(0.3)), "action_logprob"),
    (lambda r: dataclasses.replace(r, acting_policy="ai1", probs_ai1=None), "probs_ai1 is null"),
    (lambda r: dataclasses.replace(r, action_values=(1.0,)), "action_values has 1"),
    (lambda r: dataclasses.replace(r, action_logprob=math.nan), "action_logprob must be finite"),
    (lambda r: dataclasses.replace(r, action_values=(math.inf, 0.0, 0.0, 0.0)), "action_values must be finite"),
    (lambda r: _obs(r, legal_action_mask=(True, True)), "legal_action_mask has 2"),
    (lambda r: _obs(r, street="flop"), "street=flop needs 3"),
    (lambda r: _obs(r, board=("As", "2c", "3d"), street="flop"), "appears twice"),
    (lambda r: _obs(r, hero_seat=5), "not in table_observation.seats"),
    (lambda r: _obs(r, seats=tuple(SeatInfo(i, i, 100, 0, True) for i in range(10))), "seats has 10"),
])
def test_decision_violations_are_reported(make, needle):
    errors = validate(make(_decision()))
    assert any(needle in e for e in errors), errors


def test_probability_tolerance_is_1e6():
    near = (0.2, 0.5, 0.3 + 5e-7, 0.0)
    assert validate(_decision(probs_ai0=near)) == []
    assert validate(_decision(probs_ai0=(0.2, 0.5, 0.3 + 5e-6, 0.0)))


def test_other_players_hole_cards_in_observation_are_rejected():
    # a stray card anywhere in the observation (here smuggled into a position label) is a leak
    errors = validate(_obs(_decision(), position="Qh"))
    assert any("outside own hole cards" in e for e in errors), errors
    mem = _decision(session_memory_snapshot=MemorySnapshot(1, {"7c": 1.0}))
    assert any("outside own hole cards" in e for e in validate(mem))


def test_leak_check_against_real_deal():
    r = _decision()
    deal = {0: ("Qh", "Qs"), 2: ("As", "Kd"), 3: ("7c", "2d")}
    assert validate(r, deal) == []
    stolen = _obs(r, hole_cards=("Qh", "Kd"))
    errors = validate(stolen, deal)
    assert any("other players' hole cards ['Qh']" in e for e in errors), errors
    assert any("differ from the dealt cards" in e for e in errors), errors


def test_missing_and_unknown_fields_fail_on_load():
    d = to_dict(_decision())
    del d["probs_ai0"]
    with pytest.raises(RecordError, match=r"probs_ai0: required field is missing"):
        from_dict(DecisionRecord, d)
    d = to_dict(_decision())
    del d["table_observation"]["legal_action_mask"]
    with pytest.raises(RecordError, match="legal_action_mask: required"):
        from_dict(DecisionRecord, d)
    d = to_dict(_decision())
    d["table_observation"]["opponent_cards"] = ["Qh", "Qs"]
    with pytest.raises(RecordError, match="unknown field"):
        from_dict(DecisionRecord, d)
    d = to_dict(_decision())
    d["table_observation"]["pot"] = 250.5
    with pytest.raises(RecordError, match="expected an integer"):
        from_dict(DecisionRecord, d)


def test_hand_record_rules():
    assert validate(_hand()) == []
    bad = _hand(players=(PlayerHandOutcome(4, 0, 1500, 1750, 250), PlayerHandOutcome(2, 2, 2000, 1800, -200)))
    assert any("conserved" in e for e in validate(bad))
    gone = _hand(players=(PlayerHandOutcome(4, 0, 1500, 3500, 2000), PlayerHandOutcome(2, 2, 2000, 0, -2000)))
    assert any("busted" in e for e in validate(gone))
    assert validate(dataclasses.replace(gone, busted=(2,), terminal_flag=True)) == []


def test_game_record_reward_is_prize_minus_buy_in():
    cfg = load_preset("6max_sng_wta")
    rng = np.random.default_rng(3)
    res = run_game(cfg, [_Recorder(np.random.default_rng(i)) for i in range(cfg.players)], rng)
    g = GameRecord.from_result(res, buy_in=10.0, episode_id="ep-9")
    assert validate(g) == []
    assert g.terminal_flag
    assert g.rewards == tuple(p - 10.0 for p in res.prizes)
    assert any("reward" in e for e in validate(dataclasses.replace(g, rewards=g.prizes)))
    assert any("terminal_flag" in e for e in validate(dataclasses.replace(g, terminal_flag=False)))


class _Recorder(Agent):
    """Random over the legal options of a 4-way action space (all-in rare, so games last); logs one
    DecisionRecord per decision."""

    def __init__(self, rng):
        self.rng = rng
        self.records: list[DecisionRecord] = []
        self.n = 0

    def act(self, o: Observation) -> Action:
        la = o.legal
        space = [ActionOption("fold"), ActionOption("call"),
                 ActionOption("raise", la.min_raise_to or 0), ActionOption("raise", la.max_raise_to or 0)]
        mask = [la.can_fold and la.call_amount > 0, True, la.min_raise_to is not None, la.min_raise_to is not None]
        w = [x * m for x, m in zip((1.0, 4.0, 1.0, 0.05), mask)]
        probs = tuple(x / sum(w) for x in w)
        choice = int(self.rng.choice(4, p=probs))
        self.n += 1
        self.records.append(DecisionRecord(
            ids=RecordIds("ep-0", o.game_id, o.tournament_id, o.hand_id, self.n, o.player_id, "random-v0"),
            tournament_context=TournamentContext(
                table_size=6, sb=o.sb, bb=o.bb, ante_type="none" if not o.ante else "classic", ante=o.ante,
                level=o.hand_no - 1, remaining=o.players_remaining, paid_places=o.paid_places,
                payout_vector=(100.0,) * o.paid_places, next_level=o.next_blinds,
                stacks=StackSummary.of(list(o.stacks.values()))),
            table_observation=TableObservation(
                seats=tuple(SeatInfo(s, o.seat_players[s], o.stacks[s], o.bets.get(s, 0), s in o.in_hand)
                            for s in sorted(o.stacks)),
                hero_seat=o.seat, button=o.button, position="BTN" if o.seat == o.button else "OTHER", pot=o.pot,
                hole_cards=o.hole_cards, board=o.board, street=STREET_BY_BOARD[len(o.board)],
                current_hand_actions=tuple(PublicAction(*a) for a in o.action_history),
                action_space=tuple(space), legal_action_mask=tuple(mask)),
            session_memory_snapshot=None, probs_ai0=probs, probs_ai1=None, acting_policy="ai0",
            chosen_action=choice, action_logprob=math.log(probs[choice]), action_values=None,
            policy_source=PolicySource("random")))
        a = space[choice]
        return Action(a.kind, a.amount)


def test_store_round_trip_with_manifest(tmp_path):
    cfg = load_preset("6max_sng_wta")
    agents = [_Recorder(np.random.default_rng(10 + i)) for i in range(cfg.players)]
    res = run_game(cfg, agents, np.random.default_rng(5), game_id="g-store")
    decisions = [r for a in agents for r in a.records]
    assert len(decisions) > 20
    write_manifest(tmp_path, RunManifest.create("run-1", cfg, seed=5, policy_version="random-v0"))
    with RecordWriter(tmp_path) as w:
        for r in decisions:
            w.write(r)
        w.write(_hand())
        w.write(GameRecord.from_result(res, buy_in=0.0, episode_id="ep-0"))
    loaded = load_records(tmp_path)
    assert loaded[:len(decisions)] == decisions
    assert isinstance(loaded[-1], GameRecord)
    m = read_manifest(tmp_path)
    assert m.seed == 5 and m.policy_version == "random-v0" and m.config == cfg.to_dict()
    assert m.git_sha


def test_writer_refuses_invalid_records(tmp_path):
    with RecordWriter(tmp_path) as w, pytest.raises(RecordError, match="sums to"):
        w.write(_decision(probs_ai0=(0.5, 0.5, 0.5, 0.0)))
    assert (tmp_path / RECORDS).read_text(encoding="utf-8") == ""


def test_loader_rejects_bad_lines(tmp_path):
    good = {"type": "hand", "record": to_dict(_hand())}
    cases = [
        ({"type": "hand", "record": {**to_dict(_hand()), "schema_version": 2}}, "migrate"),
        ({"type": "hint", "record": to_dict(_hand())}, "expected"),
        ({"type": "decision", "record": to_dict(_decision(probs_ai0=(1.0, 1.0, 0.0, 0.0)))}, "sums to"),
        ({"type": "decision", "record": to_dict(_decision(action_logprob=math.nan))}, "non-finite"),
        ({"type": "decision", "record": to_dict(_decision(action_values=(math.inf, 0.0, 0.0, 0.0)))}, "non-finite"),
    ]
    for obj, needle in cases:
        # json.dumps writes NaN/Infinity tokens by default, which is exactly the bad input to reject
        (tmp_path / RECORDS).write_text(json.dumps(good) + "\n" + json.dumps(obj) + "\n", encoding="utf-8")
        with pytest.raises(RecordError, match=needle) as exc:
            load_records(tmp_path)
        assert ":2:" in str(exc.value)
    (tmp_path / RECORDS).write_text("{not json\n", encoding="utf-8")
    with pytest.raises(RecordError, match="not valid JSON"):
        load_records(tmp_path)


def test_ensure_valid_raises_with_all_problems():
    with pytest.raises(RecordError) as exc:
        ensure_valid(_decision(probs_ai0=(1.0, 1.0, 0.0, 0.0), chosen_action=9))
    assert "sums to" in str(exc.value) and "must index" in str(exc.value)
