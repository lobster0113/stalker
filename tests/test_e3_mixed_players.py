"""Mixed player counts per hand (#486, ADR 0019 D): the deal option, its c1 key fields, its rules and its pod job."""
import json
import shlex
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from referee.gate_r import e3_suite as R
from stalker import train_jobs as T
from stalker.e3 import game as G
from stalker.e3 import parallel
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR, parse_mix
from stalker.tools import pod_train as P

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness" / "cloud"))
import launcher as L  # noqa: E402

MIX = (2, 3, 4, 5, 6)
C1 = dict(menu="real", raise_cap=None, ranges="average", avg_rule="own", key_variant="c1", stacks="sampled")


def _c1(seed=1, **kw):
    return E3MCCFR(seed, 5, 6, "full", **{**C1, **kw})


def _dealt(m: E3MCCFR, hands: int) -> list[G.State]:
    """The hands `m.iterate` deals, without walking them (the deal is what is under test here)."""
    out = []
    m._walk = lambda s, *a: out.append(s) if a[1] == 0 else None
    m.iterate(hands)
    return out


def _decisions(rng, s: G.State):
    while not s.done:
        yield s
        acts = G.legal(s)
        s = G.apply(s, acts[int(rng.integers(len(acts)))])


def test_default_deal_is_bit_identical_to_before_the_option():
    # Hashes taken on main before #486 (7a99d57): the default draws nothing extra, so seeded runs do not move.
    m = E3MCCFR(3, 5, 6, "full")
    m.iterate(2)
    assert m.regret_hash() == "3c545f2e7e91adfbc656edd0d518ffd8a942040387cd58d67f363409c7c2b3ae"
    assert m.state()["version"] == 1 and "player_mix" not in m.state()


@pytest.mark.slow
def test_default_c1_deal_is_bit_identical_to_before_the_option():
    m = _c1(7)
    m.iterate(2)
    assert m.regret_hash() == "e11be731f1c0928aafb1095b5b36ee052fd33c39201846070dedec47c0b504bd"
    assert m.state()["version"] == 5


def test_mixed_deal_draws_every_count_and_only_those():
    hands = _dealt(_c1(player_mix=MIX), 300)
    seen = Counter(s.n for s in hands)
    assert set(seen) == set(MIX) and min(seen.values()) >= 20, seen
    weighted = Counter(s.n for s in _dealt(_c1(player_mix=(2, 6, 6)), 300))
    assert set(weighted) == {2, 6} and weighted[6] > weighted[2]


def test_c1_key_players_and_position_names_match_the_table():
    rng = np.random.default_rng(486)
    hands = _dealt(_c1(player_mix=MIX), 300)
    names = {n: set() for n in MIX}
    for s0 in hands:
        n = s0.n
        table = K.C1_POSITIONS[n]
        assert len(table) == n == len(set(table)) and table[-1] == "BB" and "BTN" in table
        for s in _decisions(rng, s0):
            pub = K.public_key(s, s.to_act, "full", "c1")
            if pub.startswith("call|"):
                continue
            f = pub.split("|")
            assert f[1] == f"n{n}" and f[0] == table[s.to_act], (n, s.to_act, pub)
            names[n].add(f[0])
    assert names == {2: {"BTN", "BB"}, 3: {"BTN", "SB", "BB"}, 4: {"CO", "BTN", "SB", "BB"},
                     5: {"HJ", "CO", "BTN", "SB", "BB"}, 6: set(G.POSITIONS[6])}
    assert K.C1_POSITIONS[6] == G.position_names(6)   # 6-max c1 keys (every c1 run before #486) are unchanged


def test_mixed_deals_keep_blinds_and_action_order():
    for s in _dealt(_c1(player_mix=MIX), 200):
        n = s.n
        assert s.bet[n - 2:] == (G.SB, G.BB) and sum(s.bet) == G.SB + G.BB
        assert s.to_act == 0 and len(s.hole) == n   # UTG first preflop; heads-up seat 0 is the button posting SB
        btn = K.C1_POSITIONS[n].index("BTN")
        assert btn == (0 if n == 2 else n - 3)
        if n == 2:
            assert s.bet[btn] == G.SB              # heads-up the button is the small blind
        while not s.done and s.street == 0:
            s = G.apply(s, "c" if "c" in G.legal(s) else G.legal(s)[0])
        if not s.done and s.street == 1 and len(s.active()) > 1:
            first = next(p for p in G.postflop_order(n) if p in s.active())
            assert s.to_act == first
            if n == 2:
                assert s.to_act == 1                # heads-up the big blind acts first after the flop


def test_mixed_deals_replay_chip_for_chip_in_pokerkit():
    # The Gate R E3 replay on the trainer's own mixed deals (Gate R's SEATS stay 6 and 9: widening them is a
    # referee-change follow-up, #486).
    rng = np.random.default_rng(4862)
    tally = R.tally_for_e3()
    hands = _dealt(_c1(player_mix=MIX), 250)
    with G.rules("real", None):
        for h, s in enumerate(hands):
            R._quiet(R._replay, s, lambda s: G.apply(s, R._pick(rng, G.legal(s))), tally, f"{s.n}-handed mix hand {h}")
    assert tally.passed == tally.total and tally.total > 0, tally.failures[:3]


def test_checkpoint_is_version_6_and_resumes_only_the_same_mix():
    m = E3MCCFR(5, 5, 6, "basic", player_mix=(2, 3))
    m.iterate(2)
    st = json.loads(json.dumps(m.state()))
    assert st["version"] == 6 and st["player_mix"] == [2, 3]
    back = E3MCCFR.from_state(st, player_mix=(2, 3))
    m.iterate(2)
    back.iterate(2)
    assert back.regret_hash() == m.regret_hash() and back.player_mix == (2, 3)
    with pytest.raises(ValueError, match="player_mix"):
        E3MCCFR.from_state(st, player_mix=())
    with pytest.raises(ValueError, match="version 6"):
        E3MCCFR.from_state({**st, "version": 5})
    with pytest.raises(ValueError, match="version 6"):
        E3MCCFR.from_state({**st, "player_mix": []})


def test_parse_mix_and_bad_counts():
    assert parse_mix("2,3,4,5,6") == MIX and parse_mix("") == ()
    for bad in ("1,2", "2,x", "10"):
        with pytest.raises(Exception, match="player mix"):
            parse_mix(bad)
    with pytest.raises(ValueError, match="2..9"):
        E3MCCFR(player_mix=(1, 6))


@pytest.mark.slow
def test_parallel_workers_deal_the_mix():
    m = E3MCCFR(9, 5, 6, "basic", player_mix=(2, 3))
    parallel.iterate(m, 4, workers=2, batch=2)
    keys = {k.split("|")[1] for k in m.regret if k.startswith("b|")}
    assert m.iterations == 4 and keys <= {"early", "late", "blind"} and m.regret


def test_pod_job_trains_the_mix_for_90_minutes_and_passes_the_budget_check():
    job = L.load_spec(ROOT / "jobs" / "e3-tp-mid-c1-mixn-pod32.yaml")
    args = shlex.split(job.command.split("python3 -m stalker.tools.pod_train", 1)[1])
    want = {"--tier": "mid", "--players": "6", "--player-mix": "2,3,4,5,6", "--minutes": "90", "--menu": "real",
            "--ranges": "average", "--avg-rule": "own", "--key-variant": "c1", "--stacks": "sampled"}
    assert {k: args[args.index(k) + 1] for k in want} == want and "--no-raise-cap" in args
    assert '${STALKER_RESUME:+--resume-result "$STALKER_RESUME"}' in job.command
    assert job.name == "e3-tp-mid-c1-mixn-pod32" and "e3-tp-mid-c1-mixn-pod32.json" in job.result_path
    cap = L.load_cap()
    assert L.check_budget(job, [], cap, "2026-11") == 0 and job.worst_case_usd <= cap / 10
    assert P.job_name("mid", 6, "c1", MIX) == "e3-tp-mid-c1-mixn-pod" and P.job_name("mid", 6, "c1") == "e3-tp-mid-c1-pod"


@pytest.mark.slow
def test_pod_result_of_a_mix_resumes_only_the_same_mix(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "e3_evaluate", lambda m, seed: {"lbr": None})
    r = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=1, player_mix=(2, 3), **C1)
    assert r["job"] == "e3-tp-beginner3-c1-mixn-pod" and r["model"]["player_mix"] == [2, 3]
    f = tmp_path / "r.json"
    f.write_text(json.dumps(r), encoding="utf-8")
    args = ("beginner", 3, "real", None, "average", "own", "c1", "sampled")
    st, _ = P.load_resume_result(f, *args, (2, 3))
    back = E3MCCFR.from_state(st, "own", (2, 3))
    assert back.player_mix == (2, 3) and back.regret_hash() == r["regret_sha256"]
    for other in ((), (2, 3, 4)):
        with pytest.raises(SystemExit, match="job|player_mix"):
            P.load_resume_result(f, *args, other)
    bad = {**r, "job": P.job_name("beginner", 3, "c1", (2, 3)), "model": {**r["model"], "player_mix": [2, 4]}}
    f.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(SystemExit, match="player_mix"):
        P.load_resume_result(f, *args, (2, 3))
