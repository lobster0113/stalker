"""Key variant c1 (#400, ADR 0019 C): the real-play cash combined key, its version, reserved slots and jobs."""
import base64
import json
import shlex
import sys
from pathlib import Path

import numpy as np
import pytest

from stalker import train_jobs as T
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR
from stalker.tools import pod_train as P

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness" / "cloud"))
import launcher as L  # noqa: E402

FLOP_HU = ["r", "f", "f", "f", "f", "c"]    # UTG opens, the big blind calls: heads-up flop, seat 5 acts first


def _play(acts, n=6, seed=3, stacks=None):
    s = G.deal(np.random.default_rng(seed), n, stacks=stacks)
    for a in acts:
        s = G.apply(s, a)
    return s


def _fields(pub):
    return pub.split("|")


def _states(rng, n, hands, stacks=False):
    for _ in range(hands):
        s = G.deal(rng, n, stacks=G.sample_stacks(rng, n) if stacks else None)
        while not s.done:
            yield s
            acts = G.legal(s)
            s = G.apply(s, acts[rng.integers(len(acts))])


def test_full_key_layout_position_name_players_and_env_slots():
    s = _play(["r", "f", "c"])            # seat 3 (BTN) to act; UTG, CO and the blinds live
    pub = K.public_key(s, 3, "full", "c1")
    f = _fields(pub)
    assert f[:2] == ["BTN", "n6"] and "tc0" in f
    assert any(x.startswith("s") and ":" in x for x in f)          # s2 stack field
    assert "u22" in f and "hb" in f                               # before/after counts, not the seat set (#475)
    assert pub.endswith("|" + "".join(G.legal(s)))
    assert K.public_key(s, 3, "pro", "c1").startswith("p|BTN|n6|")


def test_postflop_key_has_preflop_aggressor_and_b1_hand_fields():
    s = _play(FLOP_HU)
    pub = K.public_key(s, 5, "full", "c1")
    assert _fields(pub)[0] == "BB" and "go" in _fields(pub)
    r = K.initial_ranges(6)
    steps = K.equity_steps(s, 5, r, 11, "c1", "full")
    assert np.array_equal(steps, K.equity_steps(s, 5, r, 11, "b1", "full"))   # b1 hand part, no b2 (#472)
    assert "|o" in K.key(pub, K.my_step(steps, s, 5))


def test_beginner_key_carries_players_and_env_but_no_exact_seat():
    pub = K.public_key(_play(["r", "f", "c"]), 3, "basic", "c1")
    f = _fields(pub)
    assert f[:3] == ["b", "n6", "late"] and "tc0" in f and "u22" in f
    assert not any(x in G.position_names(6) for x in f)


@pytest.mark.parametrize("depth", ["basic", "full", "pro"])
def test_reserved_slots_are_constant_in_six_max_cash_deals(depth):
    # ADR 0019 §3.2: the slots D/E use must not split C's keys, so in 6-max cash they never vary
    seen_n, seen_env, renames = set(), set(), {}
    for s in _states(np.random.default_rng(7), 6, 60, stacks=True):
        if "".join(G.legal(s)) in K.LEGAL_CALL:
            continue
        p = s.to_act
        f = _fields(K.public_key(s, p, depth, "c1"))
        seen_n.add(next(x for x in f if x.startswith("n") and x[1:].isdigit()))
        seen_env.add(next(x for x in f if x.startswith("t")))
        if depth != "basic":
            renames.setdefault(f[1 if depth == "pro" else 0], set()).add(p)
    assert seen_n == {"n6"} and seen_env == {"tc0"}
    if depth != "basic":   # the position name is a one-to-one rename of the seat
        assert all(len(v) == 1 for v in renames.values()) and len(renames) == 6


def test_env_and_player_slots_change_for_other_deals():
    s = _play(["c"], n=4)
    a = K.public_key(s, s.to_act, "full", "c1")
    with K.using_env("b", ante=True):
        b = K.public_key(s, s.to_act, "full", "c1")
    assert "n4" in _fields(a) and "tc0" in _fields(a) and "tb1" in _fields(b)
    assert K.public_key(s, s.to_act, "full", "c1") == a          # the context restores the cash env
    with pytest.raises(ValueError, match="stage"):
        with K.using_env("x"):
            pass
    hu = _play([], n=2)
    # heads-up the button posts the small blind; c1 names it BTN, as players do (#486, tp_key.C1_POSITIONS)
    assert _fields(K.public_key(hu, hu.to_act, "full", "c1"))[:2] == ["BTN", "n2"]


def test_hidden_cards_and_call_keys():
    s = _play(FLOP_HU)
    hole = list(s.hole)
    hole[0], hole[5] = hole[5], hole[0]
    assert K.public_key(s._replace(hole=tuple(hole)), 5, "full", "c1") == K.public_key(s, 5, "full", "c1")
    c = _play(["a"])
    assert K.public_key(c, c.to_act, "full", "c1") == K.public_key(c, c.to_act, "full", "")


def test_other_variants_are_untouched():
    s = _play(["r", "f", "c"])
    assert K.public_key(s, 3, "full", "b3").startswith("3|") and "u0245" in K.public_key(s, 3, "full", "b3")
    assert K.public_key(s, 3, "full", "").startswith("3|")


def test_theoretical_keys_count_c1_below_b3_times_s2():
    for depth, k in (("basic", 5), ("full", 11), ("pro", 17)):
        c1 = K.theoretical_keys(6, k, depth, "c1")
        assert c1 > K.theoretical_keys(6, k, depth, "b1")
    assert K.theoretical_keys(6, 11, "full", "c1") < K.theoretical_keys(6, 11, "full", "b3") * \
        K.theoretical_keys(6, 11, "full", "s2") // K.theoretical_keys(6, 11, "full")


@pytest.mark.slow
def test_checkpoint_carries_the_key_version_and_refuses_another():
    m = E3MCCFR(1, 5, 3, "basic", key_variant="c1", stacks="sampled")
    m.iterate(2)
    st = json.loads(json.dumps(m.state()))
    assert (st["version"], st["key_variant"], st["key_version"]) == (5, "c1", K.KEY_VERSIONS["c1"])
    r = E3MCCFR.from_state(st)
    r.iterate(1), m.iterate(1)
    assert r.policy() == m.policy()
    for bad in (None, K.KEY_VERSIONS["c1"] + 1):
        with pytest.raises(ValueError, match="version"):
            E3MCCFR.from_state({**st, "key_version": bad})
    assert "key_version" not in E3MCCFR(1, 5, 3, "basic", key_variant="b3").state()


@pytest.mark.slow
def test_c1_training_on_the_real_menu_stays_below_the_bound():
    m = E3MCCFR(1, 5, 3, "basic", "real", None, "average", avg_rule="own", key_variant="c1", stacks="sampled")
    m.iterate(4)
    keys = [k for k in m.regret if not k.startswith("call|")]
    assert keys and all("|n3|" in k and "|tc0|" in k for k in keys)


def test_ci_job_uses_every_adopted_training_choice():
    job = "e3-tp-mid-c1-w4"
    assert job in T.JOBS and job in T.RESUMABLE
    kw = T.JOBS[job].keywords
    assert {k: kw[k] for k in ("tier", "workers", "menu", "raise_cap", "ranges", "avg_rule", "key_variant",
                               "stacks")} == {"tier": "mid", "workers": 4, "menu": "real", "raise_cap": None,
                                              "ranges": "average", "avg_rule": "own", "key_variant": "c1",
                                              "stacks": "sampled"}


def _pod_args(spec):
    job = L.load_spec(spec)
    return job, shlex.split(job.command.split("python3 -m stalker.tools.pod_train", 1)[1])


@pytest.mark.parametrize("tier", ["mid", "pro"])
def test_pod_jobs_chain_on_the_c1_key_and_pass_the_budget_check(tier):
    job, args = _pod_args(ROOT / "jobs" / f"e3-tp-{tier}-c1-pod32.yaml")
    want = {"--tier": tier, "--players": "6", "--menu": "real", "--ranges": "average", "--avg-rule": "own",
            "--key-variant": "c1", "--stacks": "sampled"}
    assert {k: args[args.index(k) + 1] for k in want} == want and "--no-raise-cap" in args
    assert '${STALKER_RESUME:+--resume-result "$STALKER_RESUME"}' in job.command
    cap = L.load_cap()
    # an empty month passes; the job alone never takes more than a tenth of the cap
    assert L.check_budget(job, [], cap, "2026-11") == 0
    assert job.worst_case_usd <= cap / 10


@pytest.mark.slow
def test_pod_result_of_c1_round_trips_and_resumes_only_the_same_key(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "e3_evaluate", lambda m, seed: {"lbr": None})
    r = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=1, menu="real", raise_cap=None, ranges="average",
              avg_rule="own", key_variant="c1", stacks="sampled")
    assert r["job"] == "e3-tp-beginner3-c1-pod"
    assert (r["model"]["key_variant"], r["model"]["stacks"], r["model"]["key_version"]) == ("c1", "sampled", 1)
    f = tmp_path / "r.json"
    f.write_text(json.dumps(r), encoding="utf-8")
    st, _ = P.load_resume_result(f, "beginner", 3, "real", None, "average", "own", "c1", "sampled")
    back = E3MCCFR.from_state(st, "own")
    assert (back.key_variant, back.stacks, back.iterations) == ("c1", "sampled", r["iters"])
    assert back.regret_hash() == r["regret_sha256"]
    with pytest.raises(SystemExit, match="job"):
        P.load_resume_result(f, "beginner", 3, "real", None, "average", "own", "", "sampled")
    bad = {**r, "model": {**r["model"], "key_version": 0}}
    f.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit, match="key_version"):
        P.load_resume_result(f, "beginner", 3, "real", None, "average", "own", "c1", "sampled")
    assert base64.b64decode(r["checkpoint"]["b64"])
