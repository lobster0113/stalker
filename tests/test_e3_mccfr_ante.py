"""#886: E3MCCFR ante/stage option - BB-ante deals and the c1 key's t<stage><ante> slot (default bit-identical)."""
import hashlib
import json

import numpy as np
import pytest

from stalker.e3 import game as G
from stalker.e3 import mccfr as M
from stalker.e3 import parallel
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR

KW = dict(k=K.TIER_K["beginner"], depth=K.TIER_DEPTH["beginner"], key_variant="c1")


def avg_hash(m: E3MCCFR) -> str:
    h = hashlib.sha256()
    for k in sorted(m.avg):
        v = m.avg[k]
        if v is not None:
            h.update(k.encode() + b"\0" + np.ascontiguousarray(v, dtype="<f8").tobytes())
    return h.hexdigest()


def env_slots(m: E3MCCFR) -> set[str]:
    # c1 non-call keys carry t<stage><ante> as a field; call| keys have none
    return {f for k in m.regret if not k.startswith("call|") for f in k.split("|")
            if len(f) == 3 and f[0] == "t" and f[1] in K.STAGES and f[2] in "01"}


def test_ante_keys_read_ante_one_and_default_reads_zero():
    cash = E3MCCFR(3, n=3, **KW)
    cash.iterate(1)
    ante = E3MCCFR(3, n=3, ante=G.BB, **KW)
    ante.iterate(1)
    assert env_slots(cash) == {"tc0"}
    assert env_slots(ante) == {"tc1"}
    bubble = E3MCCFR(3, n=3, ante=G.BB, stage="b", **KW)
    bubble.iterate(1)
    assert env_slots(bubble) == {"tb1"}
    early = E3MCCFR(3, n=3, stage="e", **KW)   # a stage without an ante
    early.iterate(1)
    assert env_slots(early) == {"te0"}


def test_ante_deals_go_through_game_deal(monkeypatch):
    seen = []
    real = G.deal

    def spy(*a, **kw):
        s = real(*a, **kw)
        seen.append(s.ante)
        return s

    monkeypatch.setattr(G, "deal", spy)
    E3MCCFR(1, n=3, ante=G.BB, **KW).iterate(2)
    assert seen == [G.BB, G.BB]


def test_default_is_the_old_call_and_leaves_env_untouched(monkeypatch):
    # The default must take the pre-#886 path: no ante keyword to deal, no using_env around the walk.
    calls = []
    real = G.deal
    monkeypatch.setattr(G, "deal", lambda *a, **kw: calls.append(kw) or real(*a, **kw))
    monkeypatch.setattr(K, "using_env", lambda *a, **kw: pytest.fail("default run entered using_env"))
    E3MCCFR(1, n=3, **KW).iterate(2)
    assert calls == [{}, {}]


# Taken on main 63cf0a80, before #886: seed 7, n=3, beginner c1, 20 iterations.
C1_HASH = ("4b3a3c9f13f3088f8fc26bcc50f1198d84853ef9864d25cf55eff26af3e95162",
           "eaf6760ac5e21e5f64d8c7898ea1726df1965b5ffa8280838fa24d0cf4773bda")


@pytest.mark.slow
def test_default_c1_is_bit_identical_to_before():
    m = E3MCCFR(7, n=3, **KW)
    m.iterate(20)
    assert (m.regret_hash(), avg_hash(m)) == C1_HASH


@pytest.mark.parametrize("kw, msg", [
    (dict(ante=-1), "must not be negative"),
    (dict(ante=1.5), "chips as an int"),
    (dict(ante=True), "chips as an int"),
    (dict(stage="x"), "must be one of"),
    (dict(ante=G.BB, key_variant=""), "need key_variant 'c1'"),
    (dict(stage="b", key_variant="b1"), "need key_variant 'c1'"),
])
def test_bad_env_arguments_say_how_to_fix(kw, msg):
    with pytest.raises(ValueError, match=msg):
        E3MCCFR(0, n=3, **{**KW, **kw})


def test_non_c1_default_still_builds():
    E3MCCFR(0, n=3, k=KW["k"], depth=KW["depth"])   # ante 0 / stage c is fine for every key


def test_checkpoint_v10_resumes_bit_for_bit_and_refuses_another_env():
    a = E3MCCFR(4, n=3, ante=G.BB, stage="b", **KW)
    b = E3MCCFR(4, n=3, ante=G.BB, stage="b", **KW)
    a.iterate(2)
    b.iterate(1)
    st = json.loads(json.dumps(b.state()))
    assert "payoff" not in st
    assert (st["version"], st["ante"], st["stage"]) == (10, G.BB, "b")
    c = E3MCCFR.from_state(st, ante=G.BB, stage="b")
    assert (c.ante, c.stage) == (G.BB, "b")
    c.iterate(1)
    assert a.regret_hash() == c.regret_hash() and avg_hash(a) == avg_hash(c)
    with pytest.raises(ValueError, match="ante 100, not 0"):
        E3MCCFR.from_state(st, ante=0)
    with pytest.raises(ValueError, match="stage 'b', not 'c'"):
        E3MCCFR.from_state(st, stage="c")


def test_default_checkpoint_keeps_its_version_and_reads_as_cash():
    a = E3MCCFR(4, n=3, **KW)
    a.iterate(1)
    st = json.loads(json.dumps(a.state()))
    assert st["version"] == 4 and "ante" not in st and "stage" not in st
    b = E3MCCFR.from_state(st, ante=0, stage="c")
    assert (b.ante, b.stage) == (0, "c")
    with pytest.raises(ValueError, match="ante 0, not 100"):
        E3MCCFR.from_state(st, ante=G.BB)
    st["ante"] = G.BB   # an ante in an older version is a broken file
    with pytest.raises(ValueError, match="version 10"):
        E3MCCFR.from_state(st)


def test_v10_keeps_payoff_and_the_other_options():
    a = E3MCCFR(4, n=3, ante=G.BB, player_mix=(2, 3), stacks="sampled", avg_rule="own", avg_cap=50.0,
                payoff="icm", payouts=[0.65, 0.35], lam=0.2, **KW)
    a.iterate(2)
    st = json.loads(json.dumps(a.state()))
    assert (st["version"], st["payoff"], st["lam"]) == (10, "icm", 0.2)
    b = E3MCCFR.from_state(st, player_mix=(2, 3), avg_cap=50.0, avg_rule="own", payoff="icm", ante=G.BB)
    assert (b.player_mix, b.stacks, b.avg_cap, b.payouts, b.mix_hands) == \
        ((2, 3), "sampled", 50.0, (0.65, 0.35), a.mix_hands)


def test_icm_with_ante_conserves_the_prize_pool(monkeypatch):
    sums = []
    real = M.tournament_payoff

    def spy(s, table_stacks, payouts, lam):
        assert s.ante == G.BB
        v = real(s, table_stacks, payouts, lam)
        sums.append(float(v.sum()))
        return v

    monkeypatch.setattr(M, "tournament_payoff", spy)
    E3MCCFR(2, n=3, ante=G.BB, payoff="icm", payouts=[0.65, 0.35], **KW).iterate(2)
    assert sums and max(abs(x) for x in sums) < 1e-12


def test_parallel_runs_ante_and_stage_instead_of_refusing_them():
    # #888: the workers carry ante/stage now (#886 refused them)
    for kw, slot in ((dict(ante=G.BB), "tc1"), (dict(stage="m"), "tm0")):
        m = E3MCCFR(0, n=3, **KW, **kw)
        parallel.iterate(m, 2, workers=2, batch=1)
        assert m.iterations == 2 and env_slots(m) == {slot}


def test_cli_ante_stage_flags(capsys):
    assert M.main(["--iters", "1", "--players", "3", "--key-variant", "c1"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["ante"], out["stage"]) == (0, "c")
    assert M.main(["--iters", "1", "--players", "3", "--key-variant", "c1", "--ante", "100", "--stage", "b"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["ante"], out["stage"]) == (100, "b")
