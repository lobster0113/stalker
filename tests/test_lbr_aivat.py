"""#781: the referee LBR records an AIVAT-style corrected column next to the plain one, without moving the plain one."""
import numpy as np
import pytest

from referee.e3 import lbr as L


def _uniform(key, acts):
    return np.ones(len(acts)) / len(acts)


def _caller(key, acts):
    """Checks or calls whenever it can: the corrected column then only carries the board and deal terms."""
    p = np.zeros(len(acts))
    p[acts.index("k") if "k" in acts else acts.index("c") if "c" in acts else 0] = 1.0
    return p


@pytest.mark.parametrize("policy", [_uniform, _caller])
def test_plain_fields_are_identical_with_and_without_the_correction(policy):
    off = L.exploitability_lb(policy, 6, seed=10_001, k=5, n=3, depth="full")
    on = L.exploitability_lb(policy, 6, seed=10_001, k=5, n=3, depth="full", aivat_samples=4)
    assert set(off) == {"lbr_bb", "stderr_bb", "by_seat", "hands"}   # no new key unless asked
    assert {k: on[k] for k in off} == off
    assert set(on) - set(off) == {"aivat_lbr_bb", "aivat_stderr_bb", "aivat_samples"}
    r0 = L.lbr(policy, 1, 5, seed=7, n=2)
    r1 = L.lbr(policy, 1, 5, seed=7, n=2, aivat_samples=4)
    assert (r0.mean_bb, r0.stderr_bb) == (r1.mean_bb, r1.stderr_bb)
    assert r0.aivat_mean_bb is None and r1.aivat_mean_bb is not None


def test_correction_is_deterministic_and_matches_its_hand_list():
    a = L.lbr_hands(_uniform, 0, 8, seed=3, n=2, aivat_samples=4)
    assert a == L.lbr_hands(_uniform, 0, 8, seed=3, n=2, aivat_samples=4)
    assert L.lbr_hands(_uniform, 0, 8, seed=3, n=2)[1] is None
    r = L.lbr(_uniform, 0, 8, seed=3, n=2, aivat_samples=4)
    assert r.aivat_mean_bb == pytest.approx(float(np.mean(a[1])), abs=1e-12)
    assert r.mean_bb == pytest.approx(float(np.mean(a[0])), abs=1e-12)


@pytest.mark.slow
def test_correction_terms_have_mean_zero_on_two_players():
    # Fixed seeds, so the outcome is fixed; the bound is statistical: |mean(plain - corrected)| < 4 standard errors
    # of that difference over 2 seats x 300 hands, and the correction must cut the per-hand sd (it is not a no-op).
    plain, corr = [], []
    for seat in (0, 1):
        p, c = L.lbr_hands(_uniform, seat, 300, seed=10_001 + 101 * seat, k=5, n=2, aivat_samples=4)
        plain += p
        corr += c
    d = np.array(plain) - np.array(corr)
    se = d.std(ddof=1) / np.sqrt(len(d))
    assert abs(d.mean()) < 4 * se, (d.mean(), se)
    assert np.std(corr) < 0.8 * np.std(plain)
