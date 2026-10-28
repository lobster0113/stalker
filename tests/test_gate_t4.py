import dataclasses
import json

import pytest

from referee.gate_t import t4
from stalker.env.contract import decision_context
from stalker.tp.bottleneck import default_agent


def _blind(agent, spot):
    """Fake head input that forgets every position fact and the opponent count: T4 must catch it."""
    obs, builder = t4.observation(spot)
    dc = dataclasses.replace(decision_context(builder.build(obs)), hero_position="", position_vs_button=0,
                             opponents_to_act=0, opponent_positions=(), street_aggressor=None,
                             preflop_aggressor=None)
    return repr((sorted(agent.tp(builder.build(obs)).items()), dc))


def test_t4_spot_set_loads_with_hash_and_enough_pairs():
    pairs, sha = t4.load()
    assert len(pairs) >= t4.MIN_PAIRS and len(sha) == 64
    assert all(p["why"] for p in pairs)


def test_every_spot_becomes_a_decision_context():
    for p in t4.load()[0]:
        for side in ("a", "b"):
            obs, builder = t4.observation(p[side])
            assert decision_context(builder.build(obs)).street in {"preflop", "flop", "turn", "river"}


def test_t4_passes_for_the_registered_agent():
    passed, total, fails = t4.check_t4(default_agent())
    assert passed == total and not fails


def test_t4_catches_an_input_without_position_or_opponent_count():
    passed, total, fails = t4.check_t4(default_agent(), _blind)
    assert passed < total
    failed = {f.split(":")[1].strip().split(" ")[1] for f in fails}
    assert {"button_vs_early_position", "small_blind_vs_big_blind"} <= failed


def test_bad_spot_files_are_rejected(tmp_path):
    pairs, _ = t4.load()
    few = tmp_path / "few.json"
    few.write_text(json.dumps({"pairs": pairs[:3]}), encoding="utf-8")
    with pytest.raises(t4.SpotError, match="at least"):
        t4.load(few)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"pairs": [dict(pairs[0], a={**pairs[0]["a"], "typo": 1})] + pairs[1:]}), encoding="utf-8")
    with pytest.raises(t4.SpotError, match="unknown keys"):
        t4.load(bad)


def _dc(spot):
    obs, builder = t4.observation(spot)
    return decision_context(builder.build(obs))


def test_each_pair_changes_exactly_its_declared_fields():
    # #248 review: a pair that also changes, say, the pot is not a test of the fact it names.
    for p in t4.load()[0]:
        a, b = _dc(p["a"]), _dc(p["b"])
        changed = {f.name for f in dataclasses.fields(a) if getattr(a, f.name) != getattr(b, f.name)}
        assert changed == set(p["differs"]), (p["id"], sorted(changed ^ set(p["differs"])))


def _no_opponent_count(agent, spot):
    """Forgets only the opponent count and who they are; everything else stays."""
    obs, builder = t4.observation(spot)
    po = builder.build(obs)
    dc = dataclasses.replace(decision_context(po), opponents_to_act=0, opponent_positions=())
    return repr((sorted(agent.tp(po).items()), dc))


def test_t4_catches_an_input_without_the_opponent_count():
    _, _, fails = t4.check_t4(default_agent(), _no_opponent_count)
    failed = {f.split(":")[1].strip().split(" ")[1] for f in fails}
    assert {"heads_up_vs_multiway", "three_vs_four_way"} <= failed


def test_opener_pair_differs_in_the_preflop_aggressor():
    p = next(p for p in t4.load()[0] if p["id"] == "early_vs_button_opener")
    assert _dc(p["a"]).preflop_aggressor != _dc(p["b"]).preflop_aggressor
