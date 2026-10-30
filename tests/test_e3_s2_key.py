"""Key variants s2 / s2me (#399): TP.md §1.1 effective stack and SPR of me and every live opponent in the key."""
import json

import numpy as np
import pytest

from stalker import train_jobs as T
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR
from stalker.tp.spec import load

BB = G.BB


def _deal(stacks_bb, seed=0):
    return G.deal(np.random.default_rng(seed), len(stacks_bb), stacks=tuple(b * BB for b in stacks_bb))


def _playout_states(rng, n, stacks=None, hands=200):
    for _ in range(hands):
        s = G.deal(rng, n, stacks=stacks)
        while not s.done:
            yield s
            acts = G.legal(s)
            s = G.apply(s, acts[rng.integers(len(acts))])


def test_effective_stack_on_a_mixed_multiway_table():
    # 4-handed: UTG 30BB, BTN 200BB, SB 80BB, BB 120BB
    s = _deal((30, 200, 80, 120))
    start = [K.effective_stack(s, p, start=True) // BB for p in range(4)]
    assert start == [30, 120, 80, 120]          # the 200BB button is capped by the deepest other (120BB)
    assert K.effective_stack(s, 3) == min(119, 200) * BB    # chips behind: the big blind posted 1BB
    assert K.stack_field(s, 3, "s2") == "s7:764"              # me 100+; opponents 25-40, 100+, 60-100
    s = G.apply(s, "f")                          # UTG folds: a short stack leaving changes nobody's cap here
    s = G.apply(s, "f")                          # the button folds: now the 120BB big blind is capped by the SB
    assert K.effective_stack(s, 3, start=True) == 80 * BB
    assert K.effective_stack(s, 2, start=True) == 80 * BB
    assert K.stack_field(s, 3, "s2") == "s6:6" and K.stack_field(s, 3, "s2me") == "s6"


def test_all_in_players_do_not_cap_the_effective_stack():
    s = G.apply(_deal((250, 200, 30, 60)), "a")   # the 250BB UTG is all in
    assert s.to_act == 1 and s.stack[0] == 0
    # The button is capped by the deepest player who can still act (BB 60BB), not by the all-in UTG.
    assert K.effective_stack(s, 1, start=True) == 60 * BB
    assert K.effective_stack(s, 1) == 59 * BB
    assert K.effective_stack(s, 0) == 0           # an all-in player has nothing behind
    assert K.effective_stack(s, 0, start=True) == 200 * BB
    assert K.spr(s, 1) == pytest.approx(59 * BB / s.pot)


def test_nobody_left_to_act_gives_zero():
    s = G.apply(G.apply(_deal((50, 50)), "a"), "c")   # heads-up all in and called
    assert all(K.effective_stack(s, p) == 0 for p in range(2))


@pytest.mark.parametrize("n,stack", [(6, None), (3, 40 * BB), (9, 250 * BB)])
def test_equal_stacks_give_the_value_the_key_used_before(n, stack):
    rng = np.random.default_rng(n)
    seen = 0
    for s in _playout_states(rng, n, None if stack is None else (stack,) * n, hands=60):
        p = s.to_act
        others = [s.stack[i] for i in s.live() if i != p]
        assert K.effective_stack(s, p) == min(s.stack[p], max(others) if others else 0)
        assert K.spr_step_tp(s, p) == K.spr_step(s, p)
        assert K.effective_stack(s, p, start=True) in (0, stack or G.STACK)
        seen += 1
    assert seen > 100


def test_depth_buckets_are_the_tp_section_6_buckets():
    assert list(K.EFF_EDGES_BB) == load().data["buckets"]["effective_stack_bb"]
    assert [K.stack_bucket(b) for b in (0, 5 * BB, 5 * BB + 1, 60 * BB, 100 * BB, 100 * BB + 1, 250 * BB)] == \
        [0, 0, 1, 5, 6, 7, 7]


@pytest.mark.parametrize("n,depth", [(6, "full"), (6, "basic"), (6, "pro"), (3, "full"), (9, "full")])
def test_uniform_100bb_the_new_fields_are_constant_and_the_key_carries_the_same_information(n, depth):
    rng = np.random.default_rng(10 + n)
    fwd, back = {}, {}
    fields = set()
    for s in _playout_states(rng, n, hands=150):
        p = s.to_act
        plain = K.public_key(s, p, depth)
        for v in K.STACK_VARIANTS:
            new = K.public_key(s, p, depth, v)
            if not plain.startswith("call|"):
                fields.add((v, K.stack_field(s, p, v)))
            assert fwd.setdefault((v, plain), new) == new      # the plain key determines the new one
            assert back.setdefault((v, new), plain) == plain   # and the new one the plain one
    # One field value per variant: every depth is 100BB, and s2 lists the set {60-100BB}.
    assert fields == {("s2", "s6:6"), ("s2me", "s6")}


def test_mixed_stacks_change_preflop_keys_and_call_keys_stay():
    short, deep = _deal((20, 100, 100, 100, 100, 100)), _deal((100, 100, 100, 100, 100, 100))
    assert K.public_key(short, 0, "full") == K.public_key(deep, 0, "full")   # the plain key has no stack preflop
    assert K.public_key(short, 0, "full", "s2me") != K.public_key(deep, 0, "full", "s2me")
    mixed = _deal((100, 20, 100, 100, 100, 100))      # only an opponent is short
    assert K.public_key(mixed, 0, "full", "s2me") == K.public_key(deep, 0, "full", "s2me")
    assert K.public_key(mixed, 0, "full", "s2") != K.public_key(deep, 0, "full", "s2")
    assert "|s6:63|" in K.public_key(mixed, 0, "full", "s2")
    s = G.apply(_deal((100, 30, 100)), "a")             # a 100BB shove; the 30BB button can only call or fold
    assert "".join(G.legal(s)) == "fc"
    assert K.public_key(s, 1, "full", "s2") == K.public_key(s, 1, "full")


def test_default_key_is_unchanged_and_using_variant_reaches_public_key():
    s = _deal((40, 250, 60, 100, 20, 150))
    assert K.public_key(s, 0, "full") == K.public_key(s, 0, "full", "")
    assert "|s" not in K.public_key(s, 0, "full")
    with K.using_variant("s2"):
        assert K.public_key(s, 0, "full") == K.public_key(s, 0, "full", "s2")
    with K.using_variant("s2me"):
        assert K.public_key(s, 0, "pro") == K.public_key(s, 0, "pro", "s2me") and "|s4|" in K.public_key(s, 0, "pro")


def test_sampled_stack_training_is_reproducible_and_bounded():
    a, b, me = (E3MCCFR(4, 5, 3, "full", key_variant=v, stacks="sampled") for v in ("s2", "s2", "s2me"))
    for m in (a, b, me):
        m.iterate(5)
    assert a.policy() == b.policy()
    assert any(":" in k for k in a.regret) and not any("|s" in k and ":" in k for k in me.regret)
    assert len(a.regret) <= K.theoretical_keys(3, 5, "full", "s2")
    assert len(me.regret) <= K.theoretical_keys(3, 5, "full", "s2me")
    assert K.theoretical_keys(6, 11, "full") < K.theoretical_keys(6, 11, "full", "s2me") < \
        K.theoretical_keys(6, 11, "full", "s2")
    uniform = E3MCCFR(4, 5, 3, "full", key_variant="s2")
    uniform.iterate(5)
    assert all("|s6:6|" in k for k in uniform.regret if not k.startswith("call|"))


def test_checkpoint_keeps_sampled_stacks_as_version_5():
    m = E3MCCFR(1, 5, 3, "basic", key_variant="s2", stacks="sampled")
    m.iterate(2)
    st = json.loads(json.dumps(m.state()))
    assert (st["version"], st["stacks"], st["key_variant"]) == (5, "sampled", "s2")
    r = E3MCCFR.from_state(st)
    assert (r.stacks, r.key_variant) == ("sampled", "s2")
    r.iterate(1)
    m.iterate(1)
    assert r.policy() == m.policy()
    assert E3MCCFR(1, 5, 3, "basic", key_variant="s2").state()["version"] == 4
    with pytest.raises(ValueError, match="stacks"):
        E3MCCFR(0, 5, 3, "basic", stacks="deep")


def test_parallel_workers_train_with_sampled_stacks():
    from stalker.e3 import parallel
    m = E3MCCFR(2, 5, 3, "basic", key_variant="s2", stacks="sampled")
    parallel.iterate(m, 8, workers=2, batch=4)
    assert any("|s" in k and not k.split("|")[-3].startswith("s6") for k in m.regret if not k.startswith("call|"))


def test_s2_jobs_are_registered_resumable_and_refuse_a_uniform_checkpoint(tmp_path):
    for job, v in (("e3-tp-mid-s2-w4", "s2"), ("e3-tp-mid-s2me-w4", "s2me")):
        assert job in T.JOBS and job in T.RESUMABLE
        kw = T.JOBS[job].keywords
        assert (kw["tier"], kw["workers"], kw["key_variant"], kw["stacks"]) == ("mid", 4, v, "sampled")
    assert T.JOBS["e3-tp-mid-w4"].keywords.get("stacks", "uniform") == "uniform"
    job = "e3-tp-mid-s2-w4"
    m = E3MCCFR(1, 11, 6, "full", key_variant="s2")
    (tmp_path / f"{job}-seed1.ckpt.json").write_text(json.dumps(m.state()), encoding="utf-8")
    with pytest.raises(SystemExit, match="stacks"):
        T.JOBS[job](1, 1, tmp_path / "out", resume=tmp_path)


def test_preflop_rows_read_the_variant_keys():
    from stalker.tools.preflop_rows import first_in
    t = {"policy": {}, "k": 11, "depth": "full", "players": 6, "menu": "v1", "raise_cap": 3}
    with K.using_variant("s2me"):
        spots = first_in(t)
    assert all("|s6|" in sp["public"] for sp in spots)
