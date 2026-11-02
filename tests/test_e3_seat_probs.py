"""#507: the b1 path of `_seat_probs` gathers once instead of masking per distinct step; output must not change."""
import numpy as np

from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR


def _reference(m_, public, steps, m):
    out = np.zeros((len(steps), m))
    for v in np.unique(steps[steps >= 0]):
        out[steps == v] = m_._range_row(K.key(public, int(v)), m)
    return out


def test_b1_path_matches_per_value_mask_reference():
    rng = np.random.default_rng(7)
    mc = E3MCCFR(3, K.TIER_K["mid"], 6, K.TIER_DEPTH["mid"], "real", None, "average", avg_rule="own",
                 key_variant="c1", stacks="sampled")
    mc.iterate(20)
    for trial in range(30):
        m = int(rng.integers(2, 6))
        steps = rng.integers(-1, mc.k + 40, size=int(rng.integers(1, 400)))
        steps[0] = mc.k   # force the b1 path
        for i in range(0, len(steps), 7):
            steps[i] = -1
        public = f"pub{trial % 3}"
        assert np.array_equal(mc._seat_probs(public, steps, m), _reference(mc, public, steps, m))


def test_all_collisions_give_zero_rows():
    mc = E3MCCFR(3, K.TIER_K["mid"], 6, K.TIER_DEPTH["mid"], "real", None, "average", avg_rule="own",
                 key_variant="c1", stacks="sampled")
    steps = np.array([-1, -1, mc.k + 1])
    out = mc._seat_probs("p", steps, 3)
    assert not out[:2].any() and out[2].sum() > 0
