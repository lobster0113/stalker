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


def _eval_ranks(cnt, SH, HI, K5, K3, K2, CAT):
    """Score of a 7-card hand with no flush; depends on the rank counts only."""
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
    # Same order as the reference's np.select: straight flush, flush, quads, full house, straight, ...
    if POP[fl] >= 5:
        if SH[fl] >= 0:
            return (CAT[8] << 20) | (SH[fl] << 16)
        return (CAT[5] << 20) | K5[fl]
    return _eval_ranks(cnt, SH, HI, K5, K3, K2, CAT)


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
    Same integers (beaten, tied) and the same float expression as `stalker.e2.abstraction.ehs_table`'s
    numpy loop, so the tables are bit-identical. Faster because without a flush a combo's score depends
    only on its two ranks: each runout scores at most 91 rank pairs plus the flush combos one by one,
    and ranks (value, count) entries instead of sorting 1326 scores (#201)."""
    n = combos.shape[0]
    hand = np.empty(7, dtype=np.int64)
    cnt = np.zeros(13, dtype=np.int64)
    smask = np.zeros(4, dtype=np.int64)
    bcnt = np.zeros(13, dtype=np.int64)
    bsuit = np.zeros(4, dtype=np.int64)
    # Entries 0..168: rank pair lo*13+hi; from 169: one per flush combo.
    val = np.empty(169 + n, dtype=np.int64)
    num = np.zeros(169 + n, dtype=np.int64)
    below = np.empty(169 + n, dtype=np.int64)
    upto = np.empty(169 + n, dtype=np.int64)
    slot = np.empty(n, dtype=np.int64)
    for r in range(fulls.shape[0]):
        bcnt[:] = 0
        bsuit[:] = 0
        dealt = 0  # bit c set: card c is on this runout's board
        for j in range(5):
            c = fulls[r, j]
            dealt |= 1 << c
            bcnt[c >> 2] += 1
            bsuit[c & 3] += 1
            hand[2 + j] = c
        fs = -1  # the one suit that can make a flush (3+ of 5 board cards), if any
        for k in range(4):
            if bsuit[k] >= 3:
                fs = k
        num[:169] = 0
        nf = 0
        m = 0
        for i in range(n):
            slot[i] = -1
            if not ok[i]:
                continue
            a, b = combos[i, 0], combos[i, 1]
            if (dealt >> a) & 1 or (dealt >> b) & 1:
                acc[i] += 0.5
                continue
            m += 1
            if fs >= 0 and bsuit[fs] + ((a & 3) == fs) + ((b & 3) == fs) >= 5:
                hand[0], hand[1] = a, b
                e = 169 + nf
                nf += 1
                val[e] = _eval_one(hand, SH, POP, HI, K5, K3, K2, CAT, cnt, smask)
                num[e] = 1
                slot[i] = e
                continue
            ra, rb = a >> 2, b >> 2
            e = min(ra, rb) * 13 + max(ra, rb)
            if num[e] == 0:
                for t in range(13):
                    cnt[t] = bcnt[t]
                cnt[ra] += 1
                cnt[rb] += 1
                val[e] = _eval_ranks(cnt, SH, HI, K5, K3, K2, CAT)
            num[e] += 1
            slot[i] = e
        # Entries in score order; equal scores (from different entries too) form one group.
        live = np.empty(169 + nf, dtype=np.int64)
        k = 0
        for e in range(169 + nf):
            if num[e] > 0:
                live[k] = e
                k += 1
        live = live[:k]
        order = live[np.argsort(val[live])]
        g = 0
        cum = 0
        while g < k:
            h = g
            tot = 0
            while h < k and val[order[h]] == val[order[g]]:
                tot += num[order[h]]
                h += 1
            for t in range(g, h):
                below[order[t]] = cum
                upto[order[t]] = cum + tot
            cum += tot
            g = h
        for e in range(169, 169 + nf):
            num[e] = 0
        den = max(m - 1, 1)
        for i in range(n):
            e = slot[i]
            if e >= 0:
                lo = below[e]
                hi = upto[e]
                acc[i] += (lo + (hi - lo - 1) / 2) / den


def _runout_tables(combos, ok, fulls, nb, SH, POP, HI, K5, K3, K2, CAT, idx, order, lo, hi, off):
    """`stalker.e2.eq_view._runouts` for every runout (row of `fulls`, the first `nb` cards are the
    board) written flat into idx/order/lo/hi (capacity R*n) with segment offsets `off`; returns the
    used length. Same integers as the numpy version: a stable argsort of the 7-card scores and the
    left/right tie-group bounds. Without a flush a score depends only on the two ranks, so each runout
    scores at most 91 rank pairs plus the flush combos (as `_rank_runouts`) instead of all combos (#462)."""
    n = combos.shape[0]
    hand = np.empty(7, dtype=np.int64)
    cnt = np.zeros(13, dtype=np.int64)
    smask = np.zeros(4, dtype=np.int64)
    bcnt = np.zeros(13, dtype=np.int64)
    bsuit = np.zeros(4, dtype=np.int64)
    val = np.empty(169, dtype=np.int64)
    score = np.empty(n, dtype=np.int64)
    pos = 0
    off[0] = 0
    for r in range(fulls.shape[0]):
        bcnt[:] = 0
        bsuit[:] = 0
        gone = 0  # bit c set: card c is drawn by this runout (not on the given board)
        for j in range(5):
            c = fulls[r, j]
            if j >= nb:
                gone |= 1 << c
            bcnt[c >> 2] += 1
            bsuit[c & 3] += 1
            hand[2 + j] = c
        fs = -1
        for k in range(4):
            if bsuit[k] >= 3:
                fs = k
        val[:] = -1
        m = 0
        for i in range(n):
            if not ok[i]:
                continue
            a, b = combos[i, 0], combos[i, 1]
            if (gone >> a) & 1 or (gone >> b) & 1:
                continue
            if fs >= 0 and bsuit[fs] + ((a & 3) == fs) + ((b & 3) == fs) >= 5:
                hand[0], hand[1] = a, b
                sc = _eval_one(hand, SH, POP, HI, K5, K3, K2, CAT, cnt, smask)
            else:
                ra, rb = a >> 2, b >> 2
                e = min(ra, rb) * 13 + max(ra, rb)
                if val[e] < 0:
                    for t in range(13):
                        cnt[t] = bcnt[t]
                    cnt[ra] += 1
                    cnt[rb] += 1
                    val[e] = _eval_ranks(cnt, SH, HI, K5, K3, K2, CAT)
                sc = val[e]
            idx[pos + m] = i
            score[m] = sc
            m += 1
        srt = np.argsort(score[:m], kind="mergesort")  # stable, like numpy's kind="stable"
        g = 0
        while g < m:
            h = g
            while h < m and score[srt[h]] == score[srt[g]]:
                h += 1
            for t in range(g, h):
                lo[pos + srt[t]] = g
                hi[pos + srt[t]] = h
            g = h
        for t in range(m):
            order[pos + t] = srt[t]
        pos += m
        off[r + 1] = pos
    return pos


def _equity_segments(w, idx, order, lo, hi, off, acc, cnt):
    """Equity against range weights `w`, runout by runout (segment r = off[r]:off[r+1]): the same
    operations, in the same order, as the numpy loop in `stalker.e2.eq_view.equity_vs`."""
    cw = np.empty(idx.shape[0] + 1)
    for r in range(off.shape[0] - 1):
        a, b = off[r], off[r + 1]
        m = b - a
        cw[0] = 0.0
        for t in range(m):
            cw[t + 1] = cw[t] + w[idx[a + order[a + t]]]
        for t in range(m):
            i = idx[a + t]
            ww = w[i]
            below = cw[lo[a + t]]
            upto = cw[hi[a + t]]
            tot = cw[m] - ww
            tie = upto - below - ww
            if tot > 0:
                acc[i] += (below + 0.5 * tie) / tot
                cnt[i] += 1



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
    _eval_ranks = njit(cache=True)(_eval_ranks)
    _eval_one = njit(cache=True)(_eval_one)
    _eval_many = njit(cache=True)(_eval_many)
    _rank_runouts = njit(cache=True)(_rank_runouts)
    _equity_segments = njit(cache=True)(_equity_segments)
    _runout_tables = njit(cache=True)(_runout_tables)
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



def runout_tables(combos: np.ndarray, ok: np.ndarray, fulls: np.ndarray, nb: int):
    """Flat runout tables (idx, order, lo, hi, off) of `stalker.e2.eq_view._flat_runouts`, built in one compiled call (#462).
    Plain Python without numba (slow but exact)."""
    cap = fulls.shape[0] * combos.shape[0]
    idx, order, lo, hi = (np.empty(cap, dtype=np.int64) for _ in range(4))
    off = np.empty(fulls.shape[0] + 1, dtype=np.int64)
    used = _runout_tables(combos, ok, fulls, nb, _SH, _POP, _HI, _KICK5, _KICK3, _KICK2, _CAT, idx, order, lo, hi, off)
    return idx[:used].copy(), order[:used].copy(), lo[:used].copy(), hi[:used].copy(), off


def equity_segments(w, idx, order, lo, hi, off, acc, cnt) -> None:
    """Compiled range-equity accumulation (#201); plain Python without numba (slow but exact); used by the equity view (#188)."""
    _equity_segments(w, idx, order, lo, hi, off, acc, cnt)


def quantile_steps(xl: np.ndarray, wl: np.ndarray, k: int, total: float) -> np.ndarray:
    """Quantile steps for live values (#201, the TP tiers of #187). Plain Python without numba (slow but exact)."""
    out = np.empty(len(xl), dtype=np.int64)
    _quantile_steps(np.ascontiguousarray(xl, dtype=np.float64), np.ascontiguousarray(wl, dtype=np.float64), k, total, out)
    return out
