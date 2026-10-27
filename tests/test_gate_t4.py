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
    few.write_text(json.dumps({"pairs": pairs[:3]}))
    with pytest.raises(t4.SpotError, match="at least"):
        t4.load(few)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"pairs": [dict(pairs[0], a={**pairs[0]["a"], "typo": 1})] + pairs[1:]}))
    with pytest.raises(t4.SpotError, match="unknown keys"):
        t4.load(bad)
