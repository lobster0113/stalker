"""#918 (ADR 0027 decision 4 arm B): `pod_train --prior-result` seeds a fresh run's average-strategy sums."""
import base64
import gzip
import hashlib
import json
import time

import numpy as np
import pytest

from stalker.e3 import parallel
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR
from stalker.tools import pod_train as P
from tests.test_pod_train_tournament import CLI, small_eval  # noqa: F401  (fixture)

MID = (K.TIER_K["mid"], K.TIER_DEPTH["mid"])
# c1 keys as the cash mixn run writes them (`<pos>|n<players>|...|tc0|...|legal|e<step>`)
KEYS = {
    "SB|n4|0|1|0|0|2|0|tc0|s6:6|u01|hn|fcr2a|e3": ([3.0, 1.0, 0.0, 4.0], 7),
    "BB|n4|0|1|1|0|4|0|tc0|s6:6|u10|hb|fcr2a|e4": ([1.0, 1.0, 1.0, 1.0], 5000),   # cut to 1000
    "SB|n3|0|1|0|0|2|0|tc0|s6:6|u01|hn|fcr2a|e3": ([1.0, 0.0, 0.0, 0.0], 9),      # 3 players: not dealt at n4
    "call|3|e2": ([2.0, 6.0], 4),                                                 # no env slot: kept as is
    "BTN|n4|0|1|0|0|2|0|tc0|s6:6|u01|hn|fcr2a|e1": ([1.0, 2.0, 0.0, 0.0], 0),     # never visited: w = 0
}


def cash_prior(mix=(2, 3, 4, 5, 6)) -> dict:
    m = E3MCCFR(1, MID[0], 4, MID[1], "real", None, "average", avg_rule="own", key_variant="c1", player_mix=mix)
    for k, (row, v) in KEYS.items():
        m.avg[k] = np.array(row)
        if v:
            m.visits[k] = v
    return m.state()


def bubble_model(**kw) -> E3MCCFR:
    env, _ = P.tournament_env("9max_sng_503020", 4, "b", 0, 0.0, "bubble:skewed")
    args = {"menu": "real", "raise_cap": None, "key_variant": "c1"} | kw
    return E3MCCFR(1, MID[0], 4, MID[1], args["menu"], args["raise_cap"], "average", avg_rule="own",
                   key_variant=args["key_variant"], stacks="bubble:skewed", **env)


def test_zero_iteration_policy_is_the_prior_average_under_the_renamed_key():
    m = bubble_model()
    assert P.apply_prior(m, cash_prior()) == 3
    pol = m.policy()
    assert set(pol) == {"SB|n4|0|1|0|0|2|0|tb0|s6:6|u01|hn|fcr2a|e3", "BB|n4|0|1|1|0|4|0|tb0|s6:6|u10|hb|fcr2a|e4",
                        "call|3|e2"}
    np.testing.assert_allclose(pol["SB|n4|0|1|0|0|2|0|tb0|s6:6|u01|hn|fcr2a|e3"], [0.375, 0.125, 0, 0.5])
    np.testing.assert_allclose(pol["call|3|e2"], [0.25, 0.75])
    assert m.regret == {} and m.iterations == 0   # regrets start at 0


def test_weight_is_the_prior_visits_cut_at_1000():
    m = bubble_model()
    P.apply_prior(m, cash_prior())
    assert m.avg["SB|n4|0|1|0|0|2|0|tb0|s6:6|u01|hn|fcr2a|e3"].sum() == pytest.approx(7)
    assert m.avg["BB|n4|0|1|1|0|4|0|tb0|s6:6|u10|hb|fcr2a|e4"].sum() == pytest.approx(P.PRIOR_W_CAP) == 1000


def test_ante_env_gets_the_ante_one_slot():
    env, _ = P.tournament_env("9max_sng_503020", 4, "f", 0, 0.0, "uniform", ante=10)
    m = E3MCCFR(1, MID[0], 4, MID[1], "real", None, "average", avg_rule="own", key_variant="c1", **env)
    P.apply_prior(m, cash_prior())
    assert "SB|n4|0|1|0|0|2|0|tf1|s6:6|u01|hn|fcr2a|e3" in m.policy()


@pytest.mark.parametrize("model, prior, match", [
    (lambda: bubble_model(), lambda: cash_prior(mix=(2, 3)), "players"),            # never dealt 4
    (lambda: bubble_model(), lambda: {**cash_prior(), "k": MID[0] + 1}, "k "),     # another tier
    (lambda: bubble_model(), lambda: {**cash_prior(), "depth": "pro"}, "depth"),
    (lambda: bubble_model(), lambda: {**cash_prior(), "key_variant": "b1"}, "key_variant"),
    (lambda: bubble_model(), lambda: {**cash_prior(), "key_version": 99}, "key_version"),
    (lambda: bubble_model(), lambda: {**cash_prior(), "menu": "v1"}, "menu"),
    (lambda: bubble_model(), lambda: {**cash_prior(), "stage": "b", "version": 10}, "cash"),
    (lambda: E3MCCFR(1, MID[0], 4, MID[1], "real", None, key_variant="b1"),        # a key with no env slot
     lambda: {**cash_prior(), "key_variant": "b1", "key_version": None}, "c1"),
])
def test_a_prior_of_another_table_is_refused_with_the_fix(model, prior, match):
    with pytest.raises(SystemExit, match=match) as e:
        P.apply_prior(model(), prior())
    assert "pass a cash c1 policy" in str(e.value)


def test_prior_only_seeds_a_fresh_run():
    m = bubble_model()
    m.iterations = 1
    with pytest.raises(SystemExit, match="fresh run"):
        P.apply_prior(m, cash_prior())
    with pytest.raises(SystemExit, match="--prior-result"):
        P.main(["--prior-result", "p.json", "--resume-result", "r.json", "--out", "o.json"])


def test_reads_a_ci_checkpoint_and_a_gzipped_pod_result(tmp_path):
    st = cash_prior()
    ck = tmp_path / "c.ckpt.json"
    ck.write_text(json.dumps(st), encoding="utf-8")
    got, src = P.read_prior(ck)
    assert got["avg"] == st["avg"] and src["run_id"] is None and len(src["sha256"]) == 64
    m = E3MCCFR.from_state(st)
    model = {"k": m.k, "n": m.n, "depth": m.depth, "menu": m.menu, "raise_cap": m.raise_cap, "avg_rule": "own",
             "key_variant": "c1", "stacks": "uniform", "key_version": K.KEY_VERSIONS["c1"], "ranges": "average",
             "player_mix": list(m.player_mix), **m._count_state()}
    res = {"run_id": 42, "model": model, "checkpoint": {"b64": base64.b64encode(P.pack(m)).decode()}}
    gz = tmp_path / "r.bin"
    gz.write_bytes(gzip.compress(json.dumps(res).encode(), mtime=0))
    got, src = P.read_prior(gz)
    assert src["run_id"] == "42" and src["w_cap"] == 1000
    a, b = bubble_model(), bubble_model()
    P.apply_prior(a, st)
    P.apply_prior(b, got)
    assert a.policy() == b.policy()
    (tmp_path / "x.json").write_text(json.dumps({"checkpoint": None}), encoding="utf-8")
    with pytest.raises(SystemExit, match="no model"):
        P.read_prior(tmp_path / "x.json")


def test_without_prior_training_is_bit_identical_to_the_plain_loop():
    m, stats = P.train("beginner", 2, 1, 5, 3, 2, max_iters=2)
    ref = E3MCCFR(3, K.TIER_K["beginner"], 2, K.TIER_DEPTH["beginner"], "v1")
    parallel.iterate(ref, 2, 1, 2, pool=None, timing={})
    assert m.regret_hash() == ref.regret_hash() and "prior" not in stats


def test_reading_the_prior_is_on_the_training_clock(tmp_path, monkeypatch):
    ck = tmp_path / "c.ckpt.json"
    ck.write_text(json.dumps(cash_prior()), encoding="utf-8")
    slow = P.read_prior

    def read(path):
        time.sleep(0.4)
        return slow(path)

    monkeypatch.setattr(P, "read_prior", read)
    env, _ = P.tournament_env("9max_sng_503020", 4, "b", 0, 0.0, "bubble:skewed")
    # a 0.3 s budget: the 0.4 s read uses it all, so not one iteration runs
    m, stats = P.train("mid", 4, 1, 0.3 / 60, 1, 1, menu="real", raise_cap=None, ranges="average", avg_rule="own",
                       key_variant="c1", stacks="bubble:skewed", env=env, prior=ck)
    assert stats["chunk_iters"] == 0 and stats["train_seconds"] >= 0.4
    assert stats["prior"]["keys"] == 3 and stats["prior"]["read_seconds"] >= 0.4
    assert len(m.policy()) == 3


@pytest.mark.slow
def test_cli_records_the_prior_at_the_result_top_level(tmp_path, small_eval):  # noqa: F811
    ck = tmp_path / "c.ckpt.json"
    ck.write_text(json.dumps(cash_prior()), encoding="utf-8")
    out = tmp_path / "r.json"
    assert P.main([*CLI, "--prior-result", str(ck), "--out", str(out)]) == 0
    r = json.loads(out.read_text(encoding="utf-8"))
    assert r["prior"]["sha256"] == hashlib.sha256(ck.read_bytes()).hexdigest()
    assert r["prior"]["w_cap"] == 1000 and r["prior"]["keys"] == 3 and "prior" not in r["train_env"]
