"""b1 buckets and codes are bit-identical to the pre-#454 implementation (#454 criterion 1).

The digest covers only integers: the per-combo `b1_code` at depth "full" (outs, vuln and block bucket
indices; "basic" and "pro" are projections of it). The raw `hand_outs_vuln` floats are not hashed: their last bits depend
on the CPU's BLAS kernels, so a float64 byte digest differed between runners (#469). The buckets are
what keys read, and a value moves bucket only if it sits within float noise of an edge.

DIGEST was produced on main fe59189 (before #454) with, from the repo root:
    git worktree add ../old fe59189 && cp tests/test_e3_b1_fingerprint.py ../old/tests/ \
      && (cd ../old && python tests/test_e3_b1_fingerprint.py)
The script path prints the digest; the test recomputes it on the current tree (CI default path, no numba)."""
import hashlib
from types import SimpleNamespace

import numpy as np
import pytest

from stalker.e3 import tp_key as K

COUNT = 2000
DIGEST = "db43b0e5136ef100e3f288833e849db575b4db24ce34b2fed14d8fa1cacfaec8"


def _situations(count, seed=7):
    rng = np.random.default_rng(seed)
    deck = np.arange(52)
    for i in range(count):
        n_board = 3 + i % 2
        board = tuple(int(c) for c in rng.choice(deck, n_board, replace=False))
        live = [0] + sorted(int(q) for q in rng.choice(np.arange(1, 6), 1 + i % 3, replace=False))
        ranges = [rng.random(K.N) ** 3 * (rng.random(K.N) < 0.5 + 0.5 * rng.random()) for _ in range(6)]
        yield SimpleNamespace(street=n_board - 2, board=board, live=lambda live=live: live), ranges


def fingerprint(count=COUNT):
    h = hashlib.sha256()
    for s, ranges in _situations(count):
        for name in ("_NEXT_CACHE", "_EQ_CACHE"):  # _NEXT_CACHE does not exist before #454
            getattr(K, name, {}).clear()
        h.update(np.asarray(K.b1_code(s, 0, ranges, "full")).astype(np.int64).tobytes())
    return h.hexdigest()


@pytest.mark.slow
def test_b1_buckets_and_codes_match_the_pre_454_fingerprint():
    assert fingerprint() == DIGEST


@pytest.mark.slow
def test_moving_one_outs_edge_changes_the_fingerprint(monkeypatch):
    before = fingerprint(count=8)
    monkeypatch.setattr(K, "OUTS_EDGES", (1e-9, 14.0, 30.0))
    assert fingerprint(count=8) != before


if __name__ == "__main__":
    print(fingerprint())
