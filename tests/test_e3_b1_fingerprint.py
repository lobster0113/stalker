"""b1 buckets and codes are bit-identical to the pre-#454 implementation (#454 criterion 1).

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
DIGEST = "66eb75266f6b51f5e6ac8c71c7faf0337c307422551120dc6298d8fe304e7630"


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
    depths = ("basic", "pro", "full")
    for i, (s, ranges) in enumerate(_situations(count)):
        for name in ("_NEXT_CACHE", "_EQ_CACHE"):  # _NEXT_CACHE does not exist before #454
            getattr(K, name, {}).clear()
        for part in K.hand_outs_vuln(s, 0, ranges):
            h.update(np.nan_to_num(np.asarray(part, dtype=np.float64), nan=-1.0).tobytes())
        h.update(np.asarray(K.b1_code(s, 0, ranges, depths[i % 3])).astype(np.int64).tobytes())
    return h.hexdigest()


@pytest.mark.slow
def test_b1_buckets_and_codes_match_the_pre_454_fingerprint():
    assert fingerprint() == DIGEST


if __name__ == "__main__":
    print(fingerprint())
