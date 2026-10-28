"""Compiled 7-card evaluator for training inner loops (#201) — the same scores as
`stalker.core.evaluator.evaluate` and `referee.anchors.hu_equity.evaluate_batch`.

numba is an optional dependency (`pip install -e ".[fast]"`). Without it, `evaluate_batch` falls
back to the numpy implementation, so results never depend on whether numba is installed; only the
speed does. Equality with the reference is enforced by tests on random hands.
"""
from __future__ import annotations

import numpy as np

from referee.anchors import hu_equity as _ref
from stalker.core import evaluator as _ev

try:  # pragma: no cover - exercised only where numba is installed
    from numba import njit
    HAVE_NUMBA = True
except ImportError:  # pragma: no cover
    HAVE_NUMBA = False

_SH = _ref._SH.copy()
_POP = _ref._POP.copy()
_HI = _ref._HI.copy()
_KICK5 = _ref._KICK5.copy()
_KICK3 = _ref._KICK3.copy()
_KICK2 = _ref._KICK2.copy()
_CAT = np.array([_ev.HIGH, _ev.PAIR, _ev.TWO_PAIR, _ev.TRIPS, _ev.STRAIGHT, _ev.FLUSH, _ev.FULL_HOUSE,
                 _ev.QUADS, _ev.STRAIGHT_FLUSH], dtype=np.int64)


def _clear(mask, r):
    return mask & ~(1 << r) if r >= 0 else mask


def _eval_one(hand, SH, POP, HI, K5, K3, K2, CAT, cnt, smask):
    cnt[:] = 0
    smask[:] = 0
    for i in range(7):
        c = hand[i]
        r = c >> 2
        cnt[r] += 1
        smask[c & 3] |= 1 << r
    best, fl = -1, 0
    for k in range(4):
        if POP[smask[k]] > best:
            best, fl = POP[smask[k]], smask[k]
    has_fl = POP[fl] >= 5
    m4 = m3 = m2 = m1 = 0
    for r in range(13):
        if cnt[r] == 4:
            m4 |= 1 << r
        elif cnt[r] == 3:
            m3 |= 1 << r
        elif cnt[r] == 2:
            m2 |= 1 << r
        elif cnt[r] == 1:
            m1 |= 1 << r
    # Same order as the reference's np.select: straight flush, flush, quads, full house, straight, ...
    if has_fl and SH[fl] >= 0:
        return (CAT[8] << 20) | (SH[fl] << 16)
    if has_fl:
        return (CAT[5] << 20) | K5[fl]
    rank_mask = m4 | m3 | m2 | m1
    quads = HI[m4]
    if quads >= 0:
        return (CAT[7] << 20) | (quads << 16) | (HI[_clear(rank_mask, quads)] << 12)
    trips = HI[m3]
    trips2 = HI[_clear(m3, trips)] if trips >= 0 else -1
    p0 = HI[m2]
    pair_r = max(trips2, p0)
    if trips >= 0 and pair_r >= 0:
        return (CAT[6] << 20) | (trips << 16) | (pair_r << 12)
    if SH[rank_mask] >= 0:
        return (CAT[4] << 20) | (SH[rank_mask] << 16)
    if trips >= 0:
        return (CAT[3] << 20) | (trips << 16) | K2[m1]
    m2b = _clear(m2, p0) if p0 >= 0 else m2
    p1 = HI[m2b]
    if p1 >= 0:
        p2 = HI[_clear(m2b, p1)]
        rest = m1 | ((1 << p2) if p2 >= 0 else 0)
        return (CAT[2] << 20) | (p0 << 16) | (p1 << 12) | (HI[rest] << 8)
    if p0 >= 0:
        return (CAT[1] << 20) | (p0 << 16) | K3[m1]
    return (CAT[0] << 20) | K5[m1]


def _eval_many(hands, SH, POP, HI, K5, K3, K2, CAT):
    out = np.empty(hands.shape[0], dtype=np.int64)
    cnt = np.zeros(13, dtype=np.int64)    # scratch, reused for every hand
    smask = np.zeros(4, dtype=np.int64)
    for i in range(hands.shape[0]):
        out[i] = _eval_one(hands[i], SH, POP, HI, K5, K3, K2, CAT, cnt, smask)
    return out


def _rank_runouts(combos, ok, fulls, acc, SH, POP, HI, K5, K3, K2, CAT):
    """For each runout (row of `fulls`, 5 board cards): every usable combo's share of the other
    usable combos it beats (ties half), added to `acc`; combos blocked only by the runout add 0.5.
    Mirrors `stalker.e2.abstraction.ehs_table`'s numpy loop operation for operation."""
    n = combos.shape[0]
    hand = np.empty(7, dtype=np.int64)
    score = np.empty(n, dtype=np.int64)
    which = np.empty(n, dtype=np.int64)
    cnt = np.zeros(13, dtype=np.int64)
    smask = np.zeros(4, dtype=np.int64)
    for r in range(fulls.shape[0]):
        for j in range(5):
            hand[2 + j] = fulls[r, j]
        m = 0
        for i in range(n):
            if not ok[i]:
                continue
            a, b = combos[i, 0], combos[i, 1]
            blocked = False
            for j in range(5):
                if fulls[r, j] == a or fulls[r, j] == b:
                    blocked = True
            if blocked:
                acc[i] += 0.5
                continue
            hand[0], hand[1] = a, b
            score[m] = _eval_one(hand, SH, POP, HI, K5, K3, K2, CAT, cnt, smask)
            which[m] = i
            m += 1
        srt = np.sort(score[:m])
        den = max(m - 1, 1)
        for t in range(m):
            lo = np.searchsorted(srt, score[t], side="left")
            hi = np.searchsorted(srt, score[t], side="right")
            acc[which[t]] += (lo + (hi - lo - 1) / 2) / den



def _quantile_steps(xl, wl, k, total, out):
    """Quantile steps of the live values `xl` (weights `wl`, sum `total`): groups of equal values
    in sorted order; per group mass = weights added in original order (stable sort), as numpy's
    unique + bincount + cumsum of the TP-tier quantile scale (`quantile_buckets`, #187)."""
    order = np.argsort(xl, kind="mergesort")
    n = xl.shape[0]
    cum = 0.0
    g = 0
    while g < n:
        h = g
        msum = 0.0
        while h < n and xl[order[h]] == xl[order[g]]:
            msum += wl[order[h]]
            h += 1
        mass = msum / total
        cum = cum + mass
        step = int((cum - mass / 2) * k)
        if step > k - 1:
            step = k - 1
        for t in range(g, h):
            out[order[t]] = step
        g = h


if HAVE_NUMBA:
    _clear = njit(cache=True)(_clear)
    _eval_one = njit(cache=True)(_eval_one)
    _eval_many = njit(cache=True)(_eval_many)
    _rank_runouts = njit(cache=True)(_rank_runouts)
    _quantile_steps = njit(cache=True)(_quantile_steps)


def evaluate_batch(hands: np.ndarray) -> np.ndarray:
    """(n, 7) card array -> scores, identical to the reference; compiled when numba is available."""
    hands = np.ascontiguousarray(hands, dtype=np.int64)
    if not HAVE_NUMBA:
        return _ref.evaluate_batch(hands)
    return _eval_many(hands, _SH, _POP, _HI, _KICK5, _KICK3, _KICK2, _CAT)


def rank_runouts(combos: np.ndarray, ok: np.ndarray, fulls: np.ndarray, acc: np.ndarray) -> None:
    """Strength-rank accumulation for board tables (#201). Runs without numba as plain Python, but only
    usefully fast compiled; tests call it either way to check the kernel logic."""
    _rank_runouts(combos, ok, fulls, acc, _SH, _POP, _HI, _KICK5, _KICK3, _KICK2, _CAT)



def quantile_steps(xl: np.ndarray, wl: np.ndarray, k: int, total: float) -> np.ndarray:
    """Quantile steps for live values (#201, the TP tiers of #187). Plain Python without numba (slow but exact)."""
    out = np.empty(len(xl), dtype=np.int64)
    _quantile_steps(np.ascontiguousarray(xl, dtype=np.float64), np.ascontiguousarray(wl, dtype=np.float64), k, total, out)
    return out
