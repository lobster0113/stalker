import dataclasses
import json
import math

import numpy as np
import pytest

from stalker.pipeline.generate import generate, main, resolve_config
from stalker.records.schema import (
    ActionOption, DecisionRecord, MemorySnapshot, PolicySource, PublicAction, RecordIds, SeatInfo, StackSummary,
    TableObservation, TournamentContext,
)
from stalker.records.store import load_records, read_manifest
from stalker.typing.report import build_report, to_markdown
from stalker.typing.spots import category_probs, position_label, spot_key, stack_bucket


def decision(game="g0", probs=(0.0, 1.0, 0.0), remaining=9, hero_stack=1500, villain_stack=1500, position="UTG",
             street="preflop", actions=(), bets=(0, 0), memory=None, players_total=9) -> DecisionRecord:
    return DecisionRecord(
        ids=RecordIds("ep", game, "t", 1, 1, 0, "v"),
        tournament_context=TournamentContext(
            table_size=9, sb=25, bb=50, ante_type="none", ante=0, level=0, remaining=remaining, paid_places=3,
            payout_vector=(50.0, 30.0, 20.0), next_level=None, stacks=StackSummary.of([1500] * 9)),
        table_observation=TableObservation(
            seats=(SeatInfo(0, 0, hero_stack, bets[0], True), SeatInfo(1, 1, villain_stack, bets[1], True)),
            hero_seat=0, button=1, position=position, pot=75, hole_cards=("As", "Kd"), board=(), street=street,
            current_hand_actions=tuple(PublicAction(*a) for a in actions),
            action_space=(ActionOption("fold"), ActionOption("call"), ActionOption("raise", 150)),
            legal_action_mask=(True, True, True)),
        session_memory_snapshot=memory, probs_ai0=probs, probs_ai1=None, acting_policy="ai0",
        chosen_action=1, action_logprob=0.0, action_values=None, policy_source=PolicySource("t"))


def test_position_labels_short_handed():
    assert position_label([3, 7], 3, 3) == "BTN" and position_label([3, 7], 3, 7) == "BB"
    assert position_label([0, 1, 2], 0, 2) == "BB"
    assert position_label([0, 1, 2, 3], 0, 3) == "CO"
    assert position_label([0, 1], 0, 5) == "?"


def test_position_labels_nine_max():
    got = [position_label(range(9), 0, s) for s in range(9)]
    assert got == ["BTN", "SB", "BB", "UTG", "MP", "MP", "MP", "HJ", "CO"]


def test_stack_bucket_edges():
    assert [stack_bucket(x) for x in (0.5, 5, 9.99, 10, 15, 24.9, 25, 40, 200)] == [
        "<5", "5-10", "5-10", "10-15", "15-25", "15-25", "25-40", "40+", "40+"]


def test_spot_key_fields():
    k = spot_key(decision(hero_stack=1000, villain_stack=400), players=9)
    # effective stack = min(own, biggest opponent) = 400 chips = 8bb
    assert (k.stage, k.stack_bb, k.position, k.street, k.pot_type, k.profile) == (
        "early", "5-10", "UTG", "preflop", "unopened", "unknown")
    assert k.label() == "early|5-10|UTG|preflop|unopened|unknown"


@pytest.mark.parametrize("remaining,stage", [(9, "early"), (6, "mid"), (4, "bubble"), (3, "itm"), (2, "itm")])
def test_stage_single_table(remaining, stage):
    assert spot_key(decision(remaining=remaining), players=9).stage == stage


def test_pot_types():
    open_raise = [(5, "cbr", 150)]
    assert spot_key(decision(actions=open_raise, bets=(0, 150))).pot_type == "facing_open"
    assert spot_key(decision(actions=open_raise * 2, bets=(0, 450))).pot_type == "facing_3bet+"
    assert spot_key(decision(bets=(0, 1500))).pot_type == "facing_allin"
    assert spot_key(decision(street="flop", bets=(0, 100))).pot_type == "facing_bet"
    assert spot_key(decision(street="flop")).pot_type == "unopened"


def test_profile_buckets_need_enough_hands():
    def prof(hands, vpip):
        return spot_key(decision(memory=MemorySnapshot(hands, {"opp_vpip": vpip}))).profile
    assert [prof(3, 0.1), prof(20, 0.1), prof(20, 0.3), prof(20, 0.6)] == ["unknown", "tight", "normal", "loose"]


def test_unclassifiable_decisions_are_none_and_counted():
    assert spot_key(decision(position="OTHER")) is None
    rep = build_report([decision(position="OTHER"), decision(game="a"), decision(game="b")])
    assert rep["unclassified"] == {"count": 1, "ratio": pytest.approx(1 / 3)}


def test_category_probs_split_raise_and_allin():
    r = decision(hero_stack=150, probs=(0.1, 0.2, 0.7))  # raise to 150 = hero stack -> all-in
    assert category_probs(r) == pytest.approx({"fold": 0.1, "call": 0.2, "raise": 0.0, "allin": 0.7})


def _many(n_games, per_game, p_fold, rng):
    out = []
    for g in range(n_games):
        for _ in range(per_game):
            fold = float(rng.random() < p_fold)
            out.append(decision(game=f"g{g}", probs=(fold, 1 - fold, 0.0)))
    return out


def test_report_s1_pass_and_fail_by_sample_size():
    rng = np.random.default_rng(0)
    big = build_report(_many(1200, 1, 0.5, rng), seed=1)
    (cell,) = big["cells"]
    fold = cell["actions"]["fold"]
    assert cell["s1_pass"] and fold["half_width"] <= 0.05
    p = fold["mean"]
    assert fold["ess"] == pytest.approx(p * (1 - p) / ((fold["hi"] - fold["lo"]) / 2 / 1.959964) ** 2)
    assert 900 < fold["ess"] < 1500  # independent games: ESS about n
    small = build_report(_many(20, 1, 0.5, rng), seed=1)
    assert small["cells"][0]["s1_pass"] is False


def test_clustering_shrinks_ess():
    """Same decisions, but each game repeats one outcome 20 times: raw n is 400 yet ESS is about 20."""
    rng = np.random.default_rng(1)
    outcomes = [float(rng.random() < 0.5) for _ in range(20)]
    dec = [decision(game=f"g{g}", probs=(o, 1 - o, 0.0)) for g, o in enumerate(outcomes) for _ in range(20)]
    cell = build_report(dec, seed=1)["cells"][0]
    assert cell["n_decisions"] == 400
    assert cell["actions"]["fold"]["ess"] < 60
    assert cell["s1_pass"] is False


def test_deterministic_cell_passes_with_infinite_ess():
    cell = build_report([decision(game=f"g{g}") for g in range(4)], seed=1)["cells"][0]
    assert cell["s1_pass"] and cell["actions"]["call"]["ess"] is None


def test_single_game_cell_is_flagged_not_crashing():
    rep = build_report([decision(), decision()])
    assert rep["cells"][0]["status"] == "insufficient_games" and rep["cells"][0]["s1_pass"] is False
    assert "데이터 부족" in to_markdown(rep)


def test_report_is_reproducible_and_json_safe():
    dec = _many(30, 3, 0.4, np.random.default_rng(2))
    a, b = build_report(dec, seed=5), build_report(dec, seed=5)
    assert a == b
    json.dumps(a, allow_nan=False)


def test_resolve_config_alias():
    assert resolve_config("sng9").table_size == 9
    with pytest.raises(Exception, match="unknown preset"):
        resolve_config("nope")


def test_generate_writes_valid_records_and_report(tmp_path):
    cfg = resolve_config("6max_sng_wta")
    dec = generate(cfg, 2, seed=3, out=tmp_path / "run")
    assert dec
    loaded = load_records(tmp_path / "run")  # validates every record (probs, legality, no foreign hole cards)
    assert [r for r in loaded if isinstance(r, DecisionRecord)] == dec
    assert read_manifest(tmp_path / "run").seed == 3
    assert all(math.isclose(sum(r.probs_ai0), 1.0, abs_tol=1e-6) for r in dec)
    again = generate(cfg, 2, seed=3, out=tmp_path / "run_again", run_id="run")
    assert again == dec  # same seed, same run id: identical records
    rep = build_report(dec, players=cfg.players, seed=3)
    assert rep["decisions"] == len(dec) and rep["cells"]


def test_cli_writes_report_files(tmp_path, capsys):
    assert main(["--preset", "6max_sng_wta", "--n", "2", "--seed", "4", "--out", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "report.json").exists() and (tmp_path / "o" / "report.md").exists()
    assert "decisions" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["--n", "1", "--out", str(tmp_path / "x")])
