"""#336: trained E3 policy -> web policy file."""
import json

import numpy as np
import pytest

from stalker.e3.mccfr import E3MCCFR
from stalker.tools import export_web_policy as X


@pytest.mark.parametrize("p", [[1, 0, 0], [0.5, 0.5], [1 / 3] * 3, [0.001, 0.999], [0.2, 0.3, 0.1, 0.4], [0, 0],
                               [0.0025, 0.3324, 0.3324, 0.3327]])
def test_quantize_sums_to_q_within_one_step(p):
    q = X.quantize(p)
    assert sum(q) == X.Q and all(v >= 0 for v in q)
    ref = np.full(len(p), 1 / len(p)) if sum(p) == 0 else np.asarray(p) / sum(p)
    assert np.abs(np.asarray(q) / X.Q - ref).max() <= 1 / X.Q


def test_export_round_trip_keeps_every_key_and_names_the_run(tmp_path):
    m = E3MCCFR(1, 5, 3, "basic")
    m.iterate(5)
    ck = tmp_path / "c.ckpt.json"
    ck.write_text(json.dumps(m.state()), encoding="utf-8")
    sm = tmp_path / "s.json"
    sm.write_text(json.dumps({"job": "e3-tp-beginner", "tier": "beginner", "lbr": {"lbr_bb": 0.8, "stderr_bb": 0.2},
                              "field": {"worst": {"name": "nit5", "bb100": -30.0}}}), encoding="utf-8")
    out = tmp_path / "p.json"
    assert X.main(["--ckpt", str(ck), "--summary", str(sm), "--run", "123", "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["schema"] == X.SCHEMA and doc["run_id"] == "123" and doc["iterations"] == 5
    assert doc["tier"] == "beginner" and doc["players"] == 3 and doc["lbr_bb"] == 0.8 and doc["lbr_stderr_bb"] == 0.2
    assert doc["field_worst"]["name"] == "nit5"
    cur = m.current_policy()
    assert set(doc["policy"]) == set(cur) and doc["keys"] == len(cur)
    for k, v in cur.items():
        assert np.abs(np.asarray(doc["policy"][k]) / X.Q - np.asarray(v)).max() <= 1 / X.Q


def test_played_actions_never_quantize_to_zero():
    # #340 review: largest remainder alone gives [0, 85, 85, 85] here
    q = X.quantize([0.0025, 0.3324, 0.3324, 0.3327])
    assert q[0] >= 1 and sum(q) == X.Q
    assert X.quantize([1e-9, 1 - 1e-9]) == [1, 254] and X.quantize([0, 1]) == [0, 255]


def test_size_cap_and_pruning(tmp_path):
    m = E3MCCFR(1, 5, 3, "basic")
    m.iterate(20)
    ck = tmp_path / "c.ckpt.json"
    ck.write_text(json.dumps(m.state()), encoding="utf-8")
    out = tmp_path / "p.json"
    with pytest.raises(SystemExit, match="--min-visits"):
        X.main(["--ckpt", str(ck), "--out", str(out), "--max-bytes", "100"])
    X.main(["--ckpt", str(ck), "--out", str(out), "--min-visits", "3"])
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["keys_dropped"] > 0 and doc["min_visits"] == 3
    assert all(m.visits[k] >= 3 for k in doc["policy"])


def test_average_strategy_and_pod_result_input(tmp_path):
    # #355: export the average strategy, straight from a pod training result
    from stalker.tools import pod_train as P

    r = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=2)
    res = tmp_path / "pod.json"
    res.write_text(json.dumps(r), encoding="utf-8")
    out = tmp_path / "p.json"
    assert X.main(["--pod-result", str(res), "--strategy", "average", "--run", "9", "--out", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["strategy"] == "average" and doc["lbr_bb"] == r["lbr_average"]["lbr_bb"]
    assert doc["iterations"] == r["iters"] and doc["field_worst"] is None
    m = E3MCCFR.from_state(P.unpack_state(__import__("base64").b64decode(r["checkpoint"]["b64"]), r["model"]))
    assert set(doc["policy"]) <= set(m.policy()) and doc["keys"] == len(m.policy())
