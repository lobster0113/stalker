"""Strategy browser data (#189): per-node, per-hand-class strategies of exactly solved spots.

Like a solver viewer: pick a spot, choose each player's action in turn, and see how the player to act
plays every one of the 169 hand classes, with both players' ranges (reach probabilities) at that
node. Each node carries the GTO strategy and, where trained, the TP-GTO tier policies, so the page
can compare "what GTO does" with "what a beginner / mid / pro TP can express".

Spots (all exact in their model, Gate Q: only these may be called GTO):
- E1  heads-up push/fold, chip EV (`referee.anchors.pushfold`, cached equilibrium)
- E1b heads-up open / 3-bet-shove tree, chip EV (`stalker.e1.open_shove`)
- E1m 3-handed push/fold, ICM (`referee.anchors.icm_reference`)

EV is per class, conditional on holding it and reaching the node, against the GTO opponents:
bb for chip EV, % of the prize pool for ICM.

    python -m stalker.browser.export --out web/demo/strategies.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from referee.anchors import icm_reference as R
from referee.anchors import pushfold as P
from stalker.core.cards import HAND_CLASSES

SCHEMA_VERSION = 1
TIERS = ("beginner", "mid", "pro")


def _r(a, nd: int = 3) -> list:
    return np.round(np.asarray(a, dtype=float), nd).tolist()


def _cols(*cols) -> list:
    """Per class rows [p_action0, p_action1, ...] from per-action columns."""
    return _r(np.stack(cols, axis=1))


class _Tree:
    def __init__(self):
        self.nodes: dict[str, dict] = {}

    def decision(self, nid, seat, actions, gto, reach, ev=None, tiers=None, note=None, tp=None):
        n = {"seat": seat, "actions": [a for a, _ in actions], "next": {a: nxt for a, nxt in actions},
             "strategy": {"gto": gto, **(tiers or {})},
             # Seats that have not acted yet hold every hand: omitted (the page reads a missing range as 1).
             "reach": {k: _r(v) for k, v in reach.items() if not np.all(np.asarray(v) == 1.0)}}
        if ev is not None:
            n["ev"] = np.round(np.asarray(ev, dtype=float), 2).tolist()
        if note:
            n["note"] = note
        if tp:
            n["tp"] = tp  # per-class TP values that explain the answer (item id -> 169 values, %)
        self.nodes[nid] = n

    def terminal(self, nid, text):
        self.nodes[nid] = {"terminal": text}


def _eq_vs(e: np.ndarray, p: np.ndarray, w: np.ndarray, axis: int) -> np.ndarray:
    """Equity of each class against an opponent range `w` (per class), exact card removal via `p`.
    axis=1: rows are my classes (e[mine, theirs]); axis=0: columns are my classes (e is the row seat's)."""
    if axis == 1:
        W = p * w[None, :]
        num, den = (W * e).sum(axis=1), W.sum(axis=1)
    else:
        W = p * w[:, None]
        num, den = (W * (1 - e)).sum(axis=0), W.sum(axis=0)
    return np.divide(num, den, out=np.full(169, 0.5), where=den > 0)


def _need(call: float, pot_after: float) -> float:
    """Chip-EV required equity to call: what I put in over the final pot."""
    return call / pot_after


def hu_pushfold(stack: float, ante: float = 0.0, tiers: bool = True) -> dict:
    push, call = P.strategy(stack, ante)
    p, sb_call, bb_gain = P._payoffs(stack, ante)
    pu, _ = P._sb_values(call, p, sb_call, ante)
    pa = p.sum(axis=1)
    shove_ev = pu / pa
    g = P._bb_gain(push, p, bb_gain)
    mass_b = (p * push[:, None]).sum(axis=0)
    bb_fold = -(1.0 + ante)
    bb_call_ev = bb_fold + np.divide(g, mass_b, out=np.zeros(169), where=mass_b > 0)
    tier_sb, tier_bb = {}, {}
    if tiers:
        from stalker.e1 import tp_pushfold as T

        for t in TIERS:
            r = T.train(stack, ante, t, iters=3000, sb_view="called", scale="quantile")
            tier_sb[f"tp_{t}"] = _cols(1 - r.push, r.push)
            tier_bb[f"tp_{t}"] = _cols(1 - r.call, r.call)
    e, _ = P._tables()
    called = (p * call[None, :]).sum(axis=1)
    sb_tp = {"plan.foldeq": _r(100 * (1 - called / pa), 1), "hand.equity": _r(100 * _eq_vs(e, p, call, 1), 1)}
    need = _need(stack - 1.0, 2 * stack + ante)
    bb_tp = {"hand.equity": _r(100 * _eq_vs(e, p, push, 0), 1), "need": round(100 * need, 1)}
    tr = _Tree()
    one = np.ones(169)
    tr.decision("", "SB", [("Fold", "f"), ("All-in", "a")], _cols(1 - push, push), {"SB": one, "BB": one},
                ev=_cols(np.full(169, P.SB_FOLD), shove_ev), tiers=tier_sb, tp=sb_tp)
    tr.terminal("f", "SB 폴드 — BB가 블라인드를 가져간다")
    tr.decision("a", "BB", [("Fold", "a-f"), ("Call", "a-c")], _cols(1 - call, call), {"SB": push, "BB": one},
                ev=_cols(np.full(169, bb_fold), bb_call_ev), tiers=tier_bb, tp=bb_tp)
    tr.terminal("a-f", "BB 폴드 — SB가 팟을 가져간다")
    tr.terminal("a-c", "올인 쇼다운")
    return {"id": f"hu-pf-{stack:g}bb", "title": f"헤즈업 푸시/폴드 {stack:g}BB", "env": "E1",
            "seats": ["SB", "BB"], "stack_bb": stack, "ante_bb": ante, "value_model": "chipev", "ev_unit": "bb",
            "exact": True, "exploitability": round(P.exploitability(stack, ante, push, call), 5),
            "nodes": tr.nodes}


def hu_open_shove(stack: float, ante: float = 0.0, iters: int = 3000) -> dict:
    from stalker.e1.open_shove import Game

    g = Game(stack, ante)
    st = g.solve(iters)
    p, a, r = g.p, g.a, g.r
    mass_a = p.sum(axis=1)
    # SB root EVs under the equilibrium (not best-response continuations).
    shove = (p * (st.bbcall[None, :] * g.sb_allin + (1 - st.bbcall[None, :]) * (1 + a))).sum(axis=1) / mass_a
    vs3 = st.call3[:, None] * g.sb_allin + (1 - st.call3[:, None]) * (-r)
    opn = (p * ((1 - st.bb3[None, :]) * (1 + a) + st.bb3[None, :] * vs3)).sum(axis=1) / mass_a
    # BB versus the open.
    w_open = p * st.open[:, None]
    m_open = w_open.sum(axis=0)
    safe = lambda x, m: np.divide(x, m, out=np.zeros(169), where=m > 0)  # noqa: E731
    bb_3bet = safe((w_open * (st.call3[:, None] * g.bb_allin + (1 - st.call3[:, None]) * r)).sum(axis=0), m_open)
    bb_fold_open = np.full(169, -(1.0 + a))
    # SB versus the 3-bet shove.
    reach3 = p * st.bb3[None, :]
    sb_call3 = safe((reach3 * g.sb_allin).sum(axis=1), reach3.sum(axis=1))
    # BB versus the shove.
    w_sh = p * st.shove[:, None]
    bb_call = safe((w_sh * g.bb_allin).sum(axis=0), w_sh.sum(axis=0))
    one = np.ones(169)
    tr = _Tree()
    tr.decision("", "SB", [("Fold", "f"), (f"Open {r:g}", "o"), ("All-in", "a")], _cols(st.fold, st.open, st.shove),
                {"SB": one, "BB": one}, ev=_cols(np.full(169, -0.5), opn, shove))
    tr.terminal("f", "SB 폴드")
    tr.decision("o", "BB", [("Fold", "o-f"), ("All-in", "o-a")], _cols(1 - st.bb3, st.bb3), {"SB": st.open, "BB": one},
                ev=_cols(bb_fold_open, bb_3bet))
    tr.terminal("o-f", "BB 폴드 — SB가 블라인드를 가져간다")
    tr.decision("o-a", "SB", [("Fold", "o-a-f"), ("Call", "o-a-c")], _cols(1 - st.call3, st.call3),
                {"SB": st.open, "BB": st.bb3}, ev=_cols(np.full(169, -r), sb_call3),
                tp={"hand.equity": _r(100 * _eq_vs(g.e, p, st.bb3, 1), 1),
                    "need": round(100 * _need(stack - r, 2 * stack + a), 1)},
                note="plan.vs_raise 정답: 오픈할 때 이미 정해 두는 3벳 대응")
    tr.terminal("o-a-f", "SB 폴드 — 오픈 금액을 잃는다")
    tr.terminal("o-a-c", "올인 쇼다운")
    tr.decision("a", "BB", [("Fold", "a-f"), ("Call", "a-c")], _cols(1 - st.bbcall, st.bbcall),
                {"SB": st.shove, "BB": one}, ev=_cols(bb_fold_open, bb_call),
                tp={"hand.equity": _r(100 * _eq_vs(g.e, p, st.shove, 0), 1),
                    "need": round(100 * _need(stack - 1.0, 2 * stack + a), 1)})
    tr.terminal("a-f", "BB 폴드")
    tr.terminal("a-c", "올인 쇼다운")
    return {"id": f"hu-os-{stack:g}bb", "title": f"헤즈업 오픈/3벳 셔브 {stack:g}BB", "env": "E1b",
            "seats": ["SB", "BB"], "stack_bb": stack, "ante_bb": ante, "value_model": "chipev", "ev_unit": "bb",
            "exact": True, "exploitability": round(g.exploitability(st), 5), "nodes": tr.nodes}


def seat_names(n: int) -> list[str]:
    names = {2: ["SB", "BB"], 3: ["BTN", "SB", "BB"], 6: ["UTG", "HJ", "CO", "BTN", "SB", "BB"],
             9: ["UTG", "UTG1", "UTG2", "LJ", "HJ", "CO", "BTN", "SB", "BB"]}
    return names.get(n) or [f"EP{i}" for i in range(n - 3)] + ["BTN", "SB", "BB"]


def icm_pushfold(stack_bb: float, payouts=(0.5, 0.3, 0.2), n: int = 3, tiers: bool = True) -> dict:
    """N-handed ICM push/fold (first in moves all in or folds; callers in order; the first caller
    ends the action — `icm_reference`'s model)."""
    pay = tuple(payouts) + (0.0,) * (n - len(payouts))
    spot = R.Spot((int(stack_bb * 100),) * n, 50, 100, pay)
    # Tight tolerance: fictitious-play averages keep early mixing (AA at 96%) at the default 1e-3.
    sol = R.solve(spot, "icm", tol=1e-5, max_iter=200_000)
    st = sol.strategy
    tree = R._Tree(spot, R._value_fn(spot, "icm", 0, R.BASELINE_TOL, 5000))
    ev = tree.evaluate(st)
    pct = 100.0 / spot.prize_pool
    names = seat_names(n)
    tier_st = {}
    if tiers:
        from stalker.e1 import multiway_pushfold as M

        for t in TIERS:
            tier_st[f"tp_{t}"] = M.train(spot, "composite", t, "icm", 1500 if n <= 3 else 600).strategy
    one = np.ones(169)
    tr = _Tree()

    def unopened(nid: str, p: int):
        if p == n - 1:
            tr.terminal(nid, f"모두 폴드 — {names[-1]}가 블라인드를 가져간다")
            return
        reach = {names[i]: (1 - st.push[i]) if i < p else one for i in range(n)}
        e_push, e_fold = ev.push_ev[p]
        f_id, a_id = f"{nid}-f".lstrip("-"), f"{nid}-a".lstrip("-")
        tr.decision(nid, names[p], [("Fold", f_id), ("All-in", a_id)], _cols(1 - st.push[p], st.push[p]), reach,
                    ev=_cols(np.full(169, e_fold * pct), e_push * pct),
                    tiers={k: _cols(1 - s_.push[p], s_.push[p]) for k, s_ in tier_st.items()})
        unopened(f_id, p + 1)
        facing(a_id, p + 1, p)

    def facing(nid: str, q: int, p: int):
        if q == n:
            tr.terminal(nid, f"모두 폴드 — {names[p]}가 블라인드를 가져간다")
            return
        reach = {}
        for i in range(n):
            reach[names[i]] = (1 - st.push[i]) if i < p else st.push[p] if i == p else                 (1 - st.call[i, p]) if i < q else one
        evc, fold, _ = ev.call_ev[q, p]
        # plan.icm: chip-EV required equity vs the prize-structure (ICM) one; first caller ends the action.
        S, posts = float(spot.stacks[q]), spot.posts
        pot = 2 * S + sum(posts[i] for i in range(n) if i not in (p, q))
        win_q, lose_q = tree.lose[p, q][q], tree.win[p, q][q]
        icm_need = (fold - lose_q) / (win_q - lose_q)
        w = tree.N * st.push[p][None, :]
        eq = np.divide((w * tree.E).sum(axis=1), w.sum(axis=1), out=np.full(169, 0.5), where=w.sum(axis=1) > 0)
        tr.decision(nid, names[q], [("Fold", f"{nid}-f"), ("Call", f"{nid}-c")], _cols(1 - st.call[q, p], st.call[q, p]),
                    reach, ev=_cols(np.full(169, fold * pct), evc * pct),
                    tp={"hand.equity": _r(100 * eq, 1), "need": round(100 * (S - posts[q]) / pot, 1),
                        "need_icm": round(100 * float(icm_need), 1)},
                    tiers={k: _cols(1 - s_.call[q, p], s_.call[q, p]) for k, s_ in tier_st.items()})
        tr.terminal(f"{nid}-c", f"{names[p]} vs {names[q]} 올인 쇼다운 (첫 콜러로 액션 종료)")
        facing(f"{nid}-f", q + 1, p)

    unopened("", 0)
    pays = "/".join(f"{x:.0%}" for x in payouts)
    return {"id": f"{n}h-icm-{stack_bb:g}bb", "title": f"{n}인 ICM 푸시/폴드 {stack_bb:g}BB (상금 {pays})",
            "env": f"ICM{n}", "seats": names, "stack_bb": stack_bb, "ante_bb": 0, "value_model": "icm",
            "ev_unit": "% 상금", "exact": True, "exploitability": round(float(sol.gains.sum() / spot.prize_pool), 5),
            "nodes": tr.nodes}


def three_handed_icm(stack_bb: float, payouts=(0.5, 0.3, 0.2), tiers: bool = True) -> dict:
    return icm_pushfold(stack_bb, payouts, 3, tiers)


def export(tiers: bool = True) -> dict:
    spots = [hu_pushfold(s, tiers=tiers) for s in (5.0, 8.0, 10.0, 12.0, 15.0)]
    spots += [hu_open_shove(s) for s in (15.0, 20.0, 25.0)]
    spots += [three_handed_icm(s, tiers=tiers) for s in (10.0, 15.0)]
    spots += [icm_pushfold(s, (0.65, 0.35), 6, tiers) for s in (10.0, 15.0)]       # 6-max SNG
    spots += [icm_pushfold(s, (0.5, 0.3, 0.2), 9, tiers) for s in (10.0, 15.0)]    # 9-max SNG
    return {"schema_version": SCHEMA_VERSION, "classes": HAND_CLASSES,
            "strategy_labels": {"gto": "GTO", "tp_beginner": "TP 초보", "tp_mid": "TP 중수", "tp_pro": "TP 고수"},
            "spots": spots}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--no-tiers", action="store_true")
    a = ap.parse_args(argv)
    data = export(tiers=not a.no_tiers)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"spots": len(data["spots"]), "bytes": a.out.stat().st_size}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
