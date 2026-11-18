"""#898: tournament stack sampling for E3 training (stacks="bubble:<profile>"); defaults stay bit-identical."""
import json

import numpy as np
import pytest

from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR
from stalker.e3.tournament_stacks import sample_tournament_stacks
from stalker.tournament.config import load_preset

from test_e3_mccfr_ante import avg_hash

PRESET = "9max_sng_503020"
KW = dict(k=K.TIER_K["beginner"], depth=K.TIER_DEPTH["beginner"], key_variant="c1")
BUB = dict(stacks="bubble:random", stack_preset=PRESET, stack_remaining=4, stack_level=1)


@pytest.mark.parametrize("profile", ["even", "random", "skewed"])
def test_same_seed_same_stacks(profile):
    a = sample_tournament_stacks(np.random.default_rng(5), PRESET, 4, 0, profile)
    b = sample_tournament_stacks(np.random.default_rng(5), PRESET, 4, 0, profile)
    assert a == b and len(a) == 4 and all(isinstance(x, int) and x >= 1 for x in a)
    cfg = load_preset(PRESET)   # chips are conserved up to rounding: total / bb * BB
    assert abs(sum(a) - cfg.starting_stack * cfg.players / cfg.levels[0].bb * G.BB) <= 4


def test_even_conversion_formula():
    cfg = load_preset(PRESET)
    for level in (0, 1):
        want = (cfg.starting_stack * cfg.players / 4) / cfg.levels[level].bb * G.BB   # expected per-seat chips
        got = sample_tournament_stacks(np.random.default_rng(1), PRESET, 4, level, "even")
        assert all(abs(x - want) <= 1 for x in got), (got, want)


def test_min_chips_floor():
    st = sample_tournament_stacks(np.random.default_rng(2), PRESET, 4, 1, "skewed", min_chips=2 * G.BB)
    assert min(st) >= 2 * G.BB


def test_bubble_trains_and_rejects_bad_setup():
    m = E3MCCFR(1, n=4, **KW, **BUB)
    m.iterate(3)
    assert m.hand_stacks == () and m.iterations == 3
    for bad, msg in ((dict(n=3), "must equal stack_remaining"), (dict(stack_remaining=0), "needs stack_preset"),
                     (dict(stacks="bubble:nope"), "profile must be one of"),
                     (dict(player_mix=(4, 4)), "must equal stack_remaining")):
        with pytest.raises(ValueError, match=msg):
            E3MCCFR(1, **{"n": 4, **KW, **BUB, **bad})
    with pytest.raises(ValueError, match="only go with"):
        E3MCCFR(1, n=4, stack_preset=PRESET, **KW)


def test_checkpoint_v11_resumes_bit_for_bit_and_refuses_other_setup():
    a = E3MCCFR(4, n=4, **KW, **BUB)
    a.iterate(4)
    b = E3MCCFR(4, n=4, **KW, **BUB)
    for _ in range(2):   # save -> resume N times equals running straight through
        b.iterate(1)
        b = E3MCCFR.from_state(json.loads(json.dumps(b.state())), stack_sample=(PRESET, 4, 1))
    b.iterate(2)
    assert a.regret_hash() == b.regret_hash() and avg_hash(a) == avg_hash(b)
    st = json.loads(json.dumps(b.state()))
    assert st["version"] == 11 and st["stacks"] == "bubble:random" and st["stack_level"] == 1
    for other in ((PRESET, 4, 0), (PRESET, 3, 1), ("9max_sng_flat", 4, 1)):
        with pytest.raises(ValueError, match="dealt stacks of"):
            E3MCCFR.from_state(st, stack_sample=other)


def test_defaults_do_not_move():
    a = E3MCCFR(3, n=4, **KW)
    a.iterate(3)
    st = json.loads(json.dumps(a.state()))
    assert st["version"] == 4 and not any(k.startswith("stack_") for k in st)
    s = E3MCCFR(3, n=4, stacks="sampled", **KW)
    s.iterate(2)
    assert json.loads(json.dumps(s.state()))["version"] == 5
