"""#883: E3MCCFR payoff option - chip (default, unchanged) vs icm (prize-equity change via tournament_payoff)."""
import hashlib
import json
import time

import numpy as np
import pytest

from stalker.e3 import game as G
from stalker.e3 import mccfr as M
from stalker.e3 import parallel
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR

KW = dict(k=K.TIER_K["beginner"], depth=K.TIER_DEPTH["beginner"])


def avg_hash(m: E3MCCFR) -> str:
    h = hashlib.sha256()
    for k in sorted(m.avg):
        v = m.avg[k]
        if v is not None:
            h.update(k.encode() + b"\0" + np.ascontiguousarray(v, dtype="<f8").tobytes())
    return h.hexdigest()


# Taken on main 7f46f43e, before #883: seed 7, n=3, beginner, 30 iterations.
CHIP_HASHES = {
    "uniform": ("6ce9006a1a979cad9685fdc6d84792ac37520c1a198538b1478044a80164ef5c",
                "9392d6fe98dd3b71de0d59f08f035a5f474e38985a9d7779cf7de4d475165164"),
    "sampled": ("ebd40320afbcfa4c96f2f4ff94ce31d202df5ebbb4e5c1fa06e1037051e42c36",
                "eb7fdd61a635bff89c8acef9e66165f490e89aff8218e0b265458ad226e79a91"),
}


@pytest.mark.slow
@pytest.mark.parametrize("stacks", sorted(CHIP_HASHES))
def test_chip_default_is_bit_identical_to_before(stacks):
    m = E3MCCFR(7, n=3, stacks=stacks, **KW)
    assert m.payoff == "chip"
    m.iterate(30)
    assert (m.regret_hash(), avg_hash(m)) == CHIP_HASHES[stacks]


def test_icm_terminal_value_is_tournament_payoff(monkeypatch):
    seen = []
    real = M.tournament_payoff

    def spy(s, table_stacks, payouts, lam):
        seen.append((tuple(table_stacks), tuple(payouts), lam))
        return real(s, table_stacks, payouts, lam)

    monkeypatch.setattr(M, "tournament_payoff", spy)
    m = E3MCCFR(1, n=3, payoff="icm", payouts=[2, 1], lam=0.3, **KW)
    m.iterate(2)
    assert seen and all(p == (2 / 3, 1 / 3) and lam == 0.3 for _, p, lam in seen)
    assert all(t == (G.STACK,) * 3 for t, _, _ in seen)
    # the returned leaf value is the traverser's entry, in prize-pool units
    s = G.deal(np.random.default_rng(0), 3)
    s = G.apply(G.apply(G.apply(s, "a"), "c"), "c")
    m.hand_stacks, m._icm_cache = (G.STACK,) * 3, {}
    for trav in range(3):
        v = m._walk(s, K.initial_ranges(3), trav, [1.0] * 3)
        assert v == pytest.approx(real(s, (G.STACK,) * 3, m.payouts, 0.3)[trav])
        assert abs(v) <= 1


def test_sampled_stacks_reach_tournament_payoff(monkeypatch):
    dealt, seen = [], set()
    real_sample, real_pay = G.sample_stacks, M.tournament_payoff

    def sample(rng, n, equal_p=0.5):
        st = real_sample(rng, n, equal_p)
        dealt.append(st)
        return st

    def spy(s, table_stacks, payouts, lam):
        seen.add(tuple(table_stacks))
        return real_pay(s, table_stacks, payouts, lam)

    monkeypatch.setattr(G, "sample_stacks", sample)
    monkeypatch.setattr(M, "tournament_payoff", spy)
    m = E3MCCFR(3, n=3, stacks="sampled", payoff="icm", payouts="6max_sng_topheavy", **KW)
    m.iterate(4)
    assert len(dealt) == 4 and seen == set(dealt)


def test_icm_cache_matches_uncached():
    m = E3MCCFR(2, n=3, payoff="icm", payouts=[0.65, 0.35], **KW)
    rng = np.random.default_rng(5)
    for _ in range(20):
        s = G.random_playout(rng, 3)
        m.hand_stacks, m._icm_cache = (G.STACK,) * 3, {}
        first = m._icm(s)
        assert m._icm(s) is first
        assert np.allclose(first, M.tournament_payoff(s, m.hand_stacks, m.payouts, 0.0))


def test_wta_icm_learns_the_chip_strategy():
    # Winner-take-all ICM equity is stack / total, so with fixed 100BB tables the icm reward is the chip reward
    # times BB / total chips: a positive constant, and regret matching per infoset is scale-invariant. Equal up to
    # float rounding (1e-12); a rounding can flip a regret that is exactly 0 in one run on rare seeds, so the seed
    # is pinned (seed 7 diverges at one key after 30 iterations).
    a = E3MCCFR(1, n=3, **KW)
    b = E3MCCFR(1, n=3, payoff="icm", payouts="6max_sng_wta", **KW)
    a.iterate(10)
    b.iterate(10)
    pa, pb = a.policy(), b.policy()
    assert set(pa) == set(pb)
    assert max(np.abs(np.subtract(pa[k], pb[k])).max() for k in pa) < 1e-12


def _bb_call_prob(m, stacks):
    s = G.deal(np.random.default_rng(0), 3, stacks=stacks)
    s = G.apply(G.apply(s, "a"), "f")            # button shoves, small blind folds, the short big blind decides
    assert G.legal(s) == ["f", "c"]
    pub, pol = K.public_key(s, 2, m.depth, m.key_variant), m.policy()
    rows = [pol[K.key(pub, v)] for v in range(m.k) if K.key(pub, v) in pol]
    assert rows
    return float(np.mean([r[1] for r in rows]))


@pytest.mark.slow
def test_bubble_short_stack_calls_shoves_less_than_chip(monkeypatch):
    # 3 left, 2 paid: busting on the bubble costs the short stack its min-cash, so it calls an all in less.
    stacks = (6000, 6000, 1500)
    monkeypatch.setattr(G, "sample_stacks", lambda rng, n, equal_p=0.5: stacks)
    chip = E3MCCFR(1, n=3, stacks="sampled", **KW)
    icm = E3MCCFR(1, n=3, stacks="sampled", payoff="icm", payouts=[0.65, 0.35], **KW)
    chip.iterate(30)
    icm.iterate(30)
    c, i = _bb_call_prob(chip, stacks), _bb_call_prob(icm, stacks)
    print(f"short BB call vs shove on the bubble: chip {c:.3f} icm {i:.3f}")
    assert i < c


@pytest.mark.parametrize("kw, msg", [
    (dict(payoff="ev"), "payoff must be one of"),
    (dict(payoff="icm"), "needs payouts"),
    (dict(payoff="icm", payouts="no_such_preset"), "unknown preset"),
    (dict(payoff="icm", payouts=[0.3, 0.7]), "non-increasing"),
    (dict(payoff="icm", payouts=[0.5, -0.1]), "non-negative"),
    (dict(payoff="icm", payouts=[0, 0]), "positive total"),
    (dict(payoff="icm", payouts=[1], lam=1.5), r"\[0, 1\]"),
    (dict(payouts=[1]), "only read by payoff 'icm'"),
    (dict(lam=0.2), "only read by payoff 'icm'"),
])
def test_bad_payoff_arguments_say_how_to_fix(kw, msg):
    with pytest.raises(ValueError, match=msg):
        E3MCCFR(0, n=3, **KW, **kw)


def test_icm_player_limit(monkeypatch):
    monkeypatch.setattr(M, "MAX_EXACT_PLAYERS", 4)
    with pytest.raises(ValueError, match="exact ICM limit 4"):
        E3MCCFR(0, n=5, payoff="icm", payouts=[1], **KW)
    with pytest.raises(ValueError, match="exact ICM limit 4"):
        E3MCCFR(0, n=3, player_mix=(2, 5), payoff="icm", payouts=[1], **KW)
    E3MCCFR(0, n=4, payoff="icm", payouts=[1], **KW)


def test_payouts_preset_and_numbers_are_normalized():
    assert E3MCCFR(0, n=3, payoff="icm", payouts=[50, 30, 20], **KW).payouts == (0.5, 0.3, 0.2)
    assert E3MCCFR(0, n=6, payoff="icm", payouts="6max_sng_wta", **KW).payouts == (1.0,)
    assert E3MCCFR(0, n=3, **KW).payouts == ()


def test_parallel_runs_icm_instead_of_refusing_it():
    # #888: the workers carry the payoff now (#883 refused it); tests/test_e3_parallel_tournament.py checks the bits
    m = E3MCCFR(0, n=3, payoff="icm", payouts=[1], **KW)
    parallel.iterate(m, 2, workers=2, batch=1)
    assert m.iterations == 2 and m.regret and (m.payoff, m.payouts) == ("icm", (1.0,))


def test_checkpoint_round_trip_keeps_payoff_and_continues_bit_for_bit():
    a = E3MCCFR(4, n=3, payoff="icm", payouts=[0.65, 0.35], lam=0.25, **KW)
    a.iterate(2)
    st = json.loads(json.dumps(a.state()))
    assert (st["version"], st["payoff"], st["payouts"], st["lam"]) == (9, "icm", [0.65, 0.35], 0.25)
    b = E3MCCFR.from_state(st, payoff="icm")
    assert (b.payoff, b.payouts, b.lam) == ("icm", (0.65, 0.35), 0.25)
    a.iterate(2)
    b.iterate(2)
    assert a.regret_hash() == b.regret_hash() and avg_hash(a) == avg_hash(b)
    with pytest.raises(ValueError, match="payoff 'icm', not 'chip'"):
        E3MCCFR.from_state(st, payoff="chip")


def test_resume_keeps_payouts_whose_normalized_sum_is_not_one():
    # [54, 50, 3] normalized does not fsum to 1.0, so normalizing the saved list again moves the last bit
    a = E3MCCFR(7, n=3, payoff="icm", payouts=[54, 50, 3], **KW)
    b = E3MCCFR(7, n=3, payoff="icm", payouts=[54, 50, 3], **KW)
    a.iterate(4)
    b.iterate(2)
    c = E3MCCFR.from_state(json.loads(json.dumps(b.state())), payoff="icm")
    assert c.payouts == a.payouts
    c.iterate(2)
    assert a.regret_hash() == c.regret_hash() and avg_hash(a) == avg_hash(c)


def test_checkpoint_v9_keeps_the_other_options():
    a = E3MCCFR(4, n=3, player_mix=(2, 3), stacks="sampled", avg_rule="own", avg_cap=50.0,
                payoff="icm", payouts=[1], **KW)
    a.iterate(2)
    st = json.loads(json.dumps(a.state()))
    assert st["version"] == 9
    b = E3MCCFR.from_state(st, player_mix=(2, 3), avg_cap=50.0, avg_rule="own")
    assert (b.player_mix, b.stacks, b.avg_cap, b.mix_hands) == ((2, 3), "sampled", 50.0, a.mix_hands)


def test_old_checkpoints_read_as_chip():
    a = E3MCCFR(4, n=3, **KW)
    a.iterate(2)
    st = json.loads(json.dumps(a.state()))
    assert st["version"] == 1 and "payoff" not in st
    b = E3MCCFR.from_state(st, payoff="chip")
    assert (b.payoff, b.payouts, b.lam) == ("chip", (), 0.0)
    with pytest.raises(ValueError, match="payoff 'chip', not 'icm'"):
        E3MCCFR.from_state(st, payoff="icm")
    st["payoff"] = "icm"   # an icm payoff in an older version is a broken file
    with pytest.raises(ValueError, match="version 9"):
        E3MCCFR.from_state(st)


def test_cli_payoff_flags(capsys):
    assert M.main(["--iters", "1", "--players", "3"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["payoff"], out["payouts"], out["lam"]) == ("chip", [], 0.0)
    assert M.main(["--iters", "1", "--players", "3", "--payoff", "icm", "--payouts", "0.65,0.35", "--lam", "0.2"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["payoff"], out["payouts"], out["lam"]) == ("icm", [0.65, 0.35], 0.2)
    assert M.main(["--iters", "1", "--players", "3", "--payoff", "icm", "--payouts", "6max_sng_wta"]) == 0
    assert json.loads(capsys.readouterr().out)["payouts"] == [1.0]


@pytest.mark.slow
def test_icm_speed_ratio_six_handed():
    # Reference only (no threshold): exact 6-player ICM per distinct leaf chip change, cached per hand.
    def rate(**kw):
        m = E3MCCFR(1, n=6, **KW, **kw)
        t0 = time.perf_counter()
        m.iterate(5)
        return 5 / (time.perf_counter() - t0)

    chip, icm = rate(), rate(payoff="icm", payouts="6max_sng_topheavy")
    print(f"6-handed beginner: chip {chip:.2f} it/s, icm {icm:.2f} it/s, icm/chip {icm / chip:.2f} (reference)")
    assert icm > 0
