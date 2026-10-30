"""#391: the first-in preflop row printer reads the served table with the training keys."""
import json

from stalker.tools import preflop_rows as R


def _web(tmp_path, policy):
    d = {"schema": "stalker.web.policy", "schema_version": 1, "tier": "mid", "players": 6, "k": 11, "depth": "full",
         "iterations": 1, "run_id": "1", "strategy": "current", "q": 255, "menu": "v1", "raise_cap": 3,
         "policy": policy}
    f = tmp_path / "mid-6.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    return f


def test_rows_follow_the_training_keys_and_mark_the_hand(tmp_path):
    btn = "3|0|2|0|0|4|0|fcra|e10"
    f = _web(tmp_path, {btn: [0, 51, 204, 0]})
    t = R.load(f)
    spots = R.first_in(t, "AhAs")
    assert [s["position"] for s in spots] == ["UTG", "HJ", "CO", "BTN", "SB"]
    b = spots[3]
    assert b["public"] + "|e10" == btn and b["actions"] == ["f", "c", "r", "a"] and b["hand_step"] == 10
    assert b["rows"][10]["in_table"] and b["rows"][10]["probs"] == [0.0, 0.2, 0.8, 0.0]
    assert not b["rows"][0]["in_table"] and b["rows"][0]["probs"] == [0.25] * 4  # missing key: uniform
    text = R.render(t, spots, "AhAs")
    assert "*e10    0.0%   20.0%   80.0%    0.0%" in text


def test_ci_policy_file_needs_its_tier(tmp_path):
    f = tmp_path / "x.policy.json"
    f.write_text(json.dumps({"average": {}, "current": {}}), encoding="utf-8")
    assert R.load(f, tier="mid")["k"] == 11
    try:
        R.load(f)
    except SystemExit as e:
        assert "--tier" in str(e)
    else:
        raise AssertionError("expected SystemExit")
