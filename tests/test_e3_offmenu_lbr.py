"""#500: why c1's off-menu LBR matched the plain LBR on every seed (run 41298455592).

On the real menu the overbets the off-menu exploiter adds (referee.e3.lbr.OVERBETS, 150% / 200% pot) are
already on the menu (REAL_BET b150 / b200), so with nothing to call no extra size exists; the only off-menu
action left is the postflop min-raise facing a bet. The myopic LBR seat rarely reaches such a spot, so the
two estimates coincide unless it does. The key variant is not involved: c1 and the default key give the same
counts and values for a policy that ignores the key."""
from collections import Counter

import numpy as np
import pytest

from referee.e3 import lbr as L
from stalker.e3 import game as G
from stalker.e3 import tp_key as K


def _postflop_states(n_hands=300, seed=0):
    rng = np.random.default_rng(seed)
    with G.rules("real", None):
        for _ in range(n_hands):
            s = G.deal(rng, 6)
            while not s.done:
                if s.street > 0:
                    yield s
                acts = G.legal(s)
                s = G.apply(s, acts[int(rng.integers(len(acts)))])


def test_real_menu_off_menu_sizes_are_only_the_postflop_min_raise():
    seen = Counter()
    for s in _postflop_states():
        extra = L.extra_actions(s)
        if s.to_call() == 0:
            assert extra == [], f"real menu already has b150/b200, yet an overbet was offered: {extra}"
            seen["unopened"] += 1
        else:
            assert len(extra) <= 1
            for e in extra:
                assert e.to == max(s.bet) + s.last_raise, "facing a bet the only extra is the min-raise"
                seen["min_raise"] += 1
    assert seen["unopened"] > 20 and seen["min_raise"] > 0, seen


def _counted_lbr(monkeypatch, variant, policy, extra_sizes, seats=(0, 3, 5), hands=6):
    cnt = Counter()
    extra, step = L.extra_actions, L._step

    def counting_extra(s):
        out = extra(s)
        cnt["postflop_decisions"] += s.street > 0
        cnt["offered"] += len(out)
        return out

    def counting_step(s, a):
        cnt["chosen"] += isinstance(a, L.Extra)
        return step(s, a)

    monkeypatch.setattr(L, "extra_actions", counting_extra)
    monkeypatch.setattr(L, "_step", counting_step)
    # The e3_evaluate path (stalker.train_jobs): real menu, uncapped postflop, the key variant set for the referee.
    with G.rules("real", None), K.using_variant(variant):
        r = L.exploitability_lb(policy, hands, seed=10_001, k=5, n=6, seats=list(seats), depth="full",
                                extra_sizes=extra_sizes)
    monkeypatch.setattr(L, "extra_actions", extra)
    monkeypatch.setattr(L, "_step", step)
    return r, cnt


def _check_or_call(key, acts):
    """Never folds and never bets: the LBR seat reaches postflop, but nobody bets into it, so no extra size exists."""
    w = np.array([1.0 if a in ("c", "k") else 0.0 for a in acts])
    return w / w.sum()


@pytest.mark.slow
def test_c1_off_menu_lbr_matches_default_key_and_plain_lbr_without_extras(monkeypatch):
    out = {}
    for variant in ("", "c1"):
        plain, _ = _counted_lbr(monkeypatch, variant, _check_or_call, False, seats=(5,), hands=3)
        off, cnt = _counted_lbr(monkeypatch, variant, _check_or_call, True, seats=(5,), hands=3)
        assert cnt["postflop_decisions"] > 0, f"{variant!r}: the LBR seat never reached postflop: {cnt}"
        assert cnt["chosen"] == 0, f"{variant!r}: nobody bets, yet an extra size was chosen: {cnt}"
        assert off == plain, f"{variant!r}: no extra size chosen, so the two LBRs must be the same deals"
        out[variant] = (plain["lbr_bb"], off["lbr_bb"], dict(cnt))
    assert out[""] == out["c1"], f"c1 changed the off-menu LBR path for a key-independent policy: {out}"


def _bet_small_and_call(key, acts):
    """Never folds, bets a third of the pot when it can, else checks or calls: the big blind sees flops facing bets."""
    w = np.array([0.0 if a == "f" else 3.0 if a == "b33" else 1.0 if a in ("c", "k") else 0.0 for a in acts])
    return w / w.sum()


@pytest.mark.slow
def test_c1_off_menu_lbr_offers_and_takes_the_min_raise_like_the_default_key(monkeypatch):
    out = {}
    for variant in ("", "c1"):
        _, cnt = _counted_lbr(monkeypatch, variant, _bet_small_and_call, True, seats=(5,), hands=3)
        assert cnt["offered"] > 0 and cnt["chosen"] > 0, f"{variant!r}: the min-raise never came up: {cnt}"
        out[variant] = dict(cnt)
    assert out[""] == out["c1"], out
