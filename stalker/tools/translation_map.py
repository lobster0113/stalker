"""Where off-menu size translation is unreliable (#417): `python -m stalker.tools.translation_map`.

A real size between two menu sizes A < B is read as A with probability f and B with 1 - f
(stalker/e3/translate.py, TP.md section 6). The reading is only as good as the policy's responses at A
and B are alike: when the next seat folds 10% to A and 70% to B, a size in between is a guess. This tool
walks a 0.1BB grid of real sizes over fixed spots (opens 2-10BB per seat, 3-bets vs a 2.5BB open,
4-bets, 5-bets, min raises, the sizes up to all in, postflop bets 10-300% pot on sample boards, short
stacks) and reports per grid point:

  neighbours  the two menu labels and the split weight f (translate.split)
  legal       every size the menu has here (game._sizes + all in) and whether it is legal at the real
              stacks (the legality mask; only legal sizes are translation candidates)
  tv          total-variation distance between the next seat's action distribution after A and after B,
              each at its own menu node (chips and the bettor's Bayes-updated range), actions grouped as
              fold / call-or-check / bet-or-raise, averaged over the next seat's range (combo weights)
  fold_gap_bb (P(fold | A) - P(fold | B)) x the pot before the bet: the bettor's immediate fold-equity
              difference between the two readings. A full rollout EV of the two readings is not computed
              (it needs every later seat's response tree; the fold-equity gap is the cheap, one-seat part)
  flag        stalker.e3.translate.high_translation_error, the pre-registered rule

Output: JSON (--out) and a summary table of the flagged size ranges per spot (stdout). Numbers are a
local run on a served table, reference only (CLAUDE.md: CI results are the measure).

    python -m stalker.tools.translation_map --policy web/app/policy/mid-6.json --out map.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from stalker.core.cards import cards as parse_cards
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3 import translate as X

STEP = 10                       # 0.1BB in chips
FLOPS = ("Ah7c2d", "KsQh9h", "6c5c4d")   # dry, broadway two-tone, low connected monotone-ish


def load_policy(path: Path) -> tuple[dict, dict]:
    d = json.loads(path.read_text(encoding="utf-8"))
    q = float(d.get("q", 255))
    meta = {k: v for k, v in d.items() if k != "policy"}
    return {k: np.asarray(v, dtype=float) / q for k, v in d["policy"].items()}, meta


class Spot:
    """A state reached by menu actions from a fixed deal, with the public ranges the policy implies."""

    def __init__(self, name: str, s: G.State, ranges: list[np.ndarray]):
        self.name, self.s, self.ranges = name, s, ranges


class Mapper:
    def __init__(self, policy: dict, k: int, depth: str, menu: str, raise_cap):
        self.policy, self.k, self.depth, self.menu, self.raise_cap = policy, k, depth, menu, raise_cap
        self.missing = 0
        self.looked = 0

    def probs(self, s: G.State, ranges: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
        """(per-combo action rows [1326, m], steps) for the seat to act, uniform where the table is silent."""
        p = s.to_act
        acts = G.legal(s)
        steps = K.equity_steps(s, p, ranges, self.k)
        pub = K.public_key(s, p, self.depth)
        out = np.zeros((len(steps), len(acts)))
        for v in np.unique(steps[steps >= 0]):
            row = self.policy.get(K.key(pub, int(v)))
            self.looked += 1
            if row is None or len(row) != len(acts):
                self.missing += 1
                row = np.full(len(acts), 1.0 / len(acts))
            out[steps == v] = row
        return out, steps

    def act(self, s: G.State, ranges: list[np.ndarray], a: str) -> tuple[G.State, list[np.ndarray]]:
        probs, _ = self.probs(s, ranges)
        i = G.legal(s).index(a)
        return G.apply(s, a), K.update_range(ranges, s.to_act, probs[:, i])

    def spot(self, name: str, actions: list[str], stack_bb: int | None = None, flop: str | None = None,
             n: int = 6) -> Spot:
        s = G.deal(np.random.default_rng(417), n, self.menu, self.raise_cap)
        if flop is not None:
            board = parse_cards(flop)
            rest = [c for c in s.deck + tuple(c for h in s.hole for c in h) if c not in board]
            hole = tuple((rest[2 * i], rest[2 * i + 1]) for i in range(n))
            s = s._replace(hole=hole, deck=tuple(board) + tuple(rest[2 * n:]))
        if stack_bb is not None:
            s = s._replace(stack=tuple(stack_bb * G.BB - b for b in s.bet))
        ranges = K.initial_ranges(n)
        for a in actions:
            if a == "/":
                continue
            s, ranges = self.act(s, ranges, a)
        return Spot(name, s, ranges)

    def response(self, s: G.State, ranges: list[np.ndarray], label: str) -> dict:
        """Next seat's fold / call / raise shares after the actor takes menu `label`: the range mixture
        and, per combo, its own shares (`per_combo`, [1326, 3]; `weight` = the next seat's range)."""
        p = s.to_act
        probs, _ = self.probs(s, ranges)
        ns = G.apply(s, label)
        nr = K.update_range(ranges, p, probs[:, G.legal(s).index(label)])
        pot_before = s.pot
        if ns.done or ns.street != s.street:
            return {"seat": None, "fold": 0.0, "call": 1.0, "raise": 0.0, "pot_before": pot_before,
                    "per_combo": None, "weight": None}
        q = ns.to_act
        rp, steps = self.probs(ns, nr)
        acts = G.legal(ns)
        group = np.zeros((len(acts), 3))
        for i, a in enumerate(acts):
            group[i, 0 if a == "f" else 1 if a in ("c", "k") else 2] = 1.0
        per = rp @ group
        w = nr[q] * (steps >= 0)
        mix = (w / w.sum()) @ per
        return {"seat": q, "fold": float(mix[0]), "call": float(mix[1]), "raise": float(mix[2]),
                "legal": "".join(acts), "pot_before": pot_before, "per_combo": per, "weight": w}


def tv(ra: dict, rb: dict) -> float:
    """TV distance of the two range mixtures."""
    return 0.5 * sum(abs(ra[c] - rb[c]) for c in ("fold", "call", "raise"))


def tv_hand(ra: dict, rb: dict) -> float:
    """Range-weighted mean of each combo's own TV distance: a mixture can match while hands swap
    actions (strong hands raise A but call B), so this is the one the calibration reads."""
    if ra["per_combo"] is None or rb["per_combo"] is None:
        return tv(ra, rb)
    w = np.minimum(ra["weight"] > 0, rb["weight"] > 0) * ra["weight"]
    d = 0.5 * np.abs(ra["per_combo"] - rb["per_combo"]).sum(axis=1)
    return float((w * d).sum() / w.sum())


def grid(m: Mapper, sp: Spot, lo: int, hi: int, step: int = STEP) -> list[dict]:
    s = sp.s
    p = s.to_act
    room = s.stack[p] + s.bet[p]
    least = min(max(s.bet) + s.last_raise, room)
    legal = set(G.legal(s))
    mask = {a: a in legal for a, _ in G._sizes(s)}
    mask["a"] = "a" in legal
    cache: dict[tuple[str, str], tuple] = {}
    rows = []
    first = max(lo, -(-least // step) * step)   # 0.1BB-aligned points, plus the min raise and all in
    amounts = sorted({least, room} | set(range(first, min(hi, room) + 1, step)))
    for to in amounts:
        sp_ = X.split(s, to)
        row = {"to": to, "bb": to / G.BB, "x": round(X.pot_fraction(s, to), 4),
               "split": [[a, round(f, 4)] for a, f in sp_], "min_raise": to == least, "all_in": to == room,
               "flag": X.high_translation_error(s, to)}
        if len(sp_) == 2:
            pair = (sp_[0][0], sp_[1][0])
            if pair not in cache:
                ra, rb = m.response(s, sp.ranges, pair[0]), m.response(s, sp.ranges, pair[1])
                cache[pair] = (tv(ra, rb), (ra["fold"] - rb["fold"]) * ra["pot_before"] / G.BB,
                               _short(ra), _short(rb), tv_hand(ra, rb))
            row["tv"] = round(cache[pair][0], 4)
            row["tv_hand"] = round(cache[pair][4], 4)
            row["fold_gap_bb"] = round(cache[pair][1], 3)
        rows.append(row)
    pairs = {f"{a}|{b}": {"tv": round(v[0], 4), "tv_hand": round(v[4], 4), "fold_gap_bb": round(v[1], 3),
                          "after": {a: v[2], b: v[3]}} for (a, b), v in cache.items()}
    return [{"spot": sp.name, "history": list(s.history), "seat": p, "room": room, "least": least,
             "legal_mask": mask, "menu": [[a, t] for a, t in X._menu(s)], "pairs": pairs, "grid": rows}]


def _short(r: dict) -> dict:
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()
            if k not in ("per_combo", "weight")}


def spots(m: Mapper) -> list[tuple[Spot, int, int]]:
    """(spot, lowest, highest street total) for every grid the issue lists (#417)."""
    n = 6
    out = []
    for seat in range(n - 1):   # UTG..SB open, folded to
        sp = m.spot(f"open {G.position_names(n)[seat]}", ["f"] * seat)
        out.append((sp, 200, 1000))
    sp = m.spot("open UTG all-in edge", [])
    out.append((sp, 7000, 10000))
    for seat in (3, 5):          # BTN and BB 3-bet vs a CO 2.5BB open
        sp = m.spot(f"3bet {G.position_names(n)[seat]} vs CO", ["f", "f", "r"] + ["f"] * (seat - 3))
        out.append((sp, 500, 3000))
    sp = m.spot("3bet BTN vs CO all-in edge", ["f", "f", "r"])
    out.append((sp, 7000, 10000))
    sp = m.spot("4bet CO vs BTN", ["f", "f", "r", "r", "f", "f"])
    out.append((sp, 1200, 4000))
    sp = m.spot("5bet BTN vs CO (capped: all in only)", ["f", "f", "r", "r", "f", "f", "r"])
    out.append((sp, 2500, 10000))
    for bb in (15, 25, 40):
        sp = m.spot(f"open BTN {bb}BB stacks", ["f", "f", "f"], stack_bb=bb)
        out.append((sp, 200, bb * G.BB))
    for flop in FLOPS:
        sp = m.spot(f"flop bet BB vs BTN {flop}", ["f", "f", "f", "r", "f", "c"], flop=flop)
        pot = sp.s.pot
        out.append((sp, G.BB, 3 * pot))
    sp = m.spot(f"flop raise BTN vs BB b33 {FLOPS[0]}", ["f", "f", "f", "r", "f", "c", "b33"], flop=FLOPS[0])
    out.append((sp, 0, 4000))
    return out


def ranges_of(rows: list[dict], key) -> list[list[float]]:
    """Contiguous [lo, hi] BB runs of grid rows where key(row) holds."""
    out: list[list[float]] = []
    for r in rows:
        if key(r):
            if out and abs(r["bb"] - out[-1][1] - STEP / G.BB) < 1e-9:
                out[-1][1] = r["bb"]
            else:
                out.append([r["bb"], r["bb"]])
    return out


def _band(r: dict) -> bool:
    lo, hi = X.F_BAND
    return len(r["split"]) == 2 and lo < r["split"][0][1] < hi


def summarize(spot: dict) -> dict:
    """Per spot: flagged size runs, and the calibration check of the rule against the policy's TV:
    `missed` = far from both sizes (f in F_BAND) with per-hand TV >= TV_HIGH but not flagged."""
    g = spot["grid"]
    two = [r for r in g if len(r["split"]) == 2]
    return {"spot": spot["spot"], "points": len(g), "split": len(two), "flagged": sum(r["flag"] for r in g),
            "flag_bb": ranges_of(g, lambda r: r["flag"]),
            "missed": sum(1 for r in g if _band(r) and r["tv_hand"] >= X.TV_HIGH and not r["flag"]),
            "max_tv_hand": max((r["tv_hand"] for r in two), default=0.0),
            "pairs": {k: [v["tv"], v["tv_hand"]] for k, v in spot["pairs"].items()},
            "illegal": [a for a, ok in spot["legal_mask"].items() if not ok]}


def table(sums: list[dict]) -> str:
    lines = [f"{'spot':40} {'pts':>4} {'split':>5} {'flag':>4} {'miss':>4}  flagged BB | pair TV mix/hand | illegal sizes"]
    for s in sums:
        runs = ", ".join(f"{a:g}-{b:g}" if a != b else f"{a:g}" for a, b in s["flag_bb"]) or "-"
        pairs = " ".join(f"{k}={v[0]:.2f}/{v[1]:.2f}" for k, v in s["pairs"].items()) or "-"
        ill = ",".join(s["illegal"]) or "-"
        lines.append(f"{s['spot']:40} {s['points']:4d} {s['split']:5d} {s['flagged']:4d} {s['missed']:4d}  "
                     f"{runs} | {pairs} | {ill}")
    return "\n".join(lines)


def build(policy_path: Path) -> dict:
    policy, meta = load_policy(policy_path)
    menu = meta.get("menu", "v1")
    cap = meta.get("raise_cap", G.RAISE_CAP)
    m = Mapper(policy, int(meta["k"]), meta["depth"], menu, cap)
    out = []
    for sp, lo, hi in spots(m):
        out.extend(grid(m, sp, lo, hi))
    return {"schema": "stalker.translation_map", "schema_version": 1,
            "policy": {k: meta.get(k) for k in ("tier", "players", "k", "depth", "iterations", "run_id", "sha")},
            "menu": menu, "raise_cap": cap,
            "rule": {"tv_high": X.TV_HIGH, "gap_high": X.GAP_HIGH, "f_band": X.F_BAND, "allin_merge": G.ALLIN_MERGE},
            "ev": "not computed: a full rollout needs every later seat's tree; fold_gap_bb is the next seat's part",
            "table_lookups": m.looked, "table_missing": m.missing,
            "spots": out, "summary": [summarize(s) for s in out]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Map where off-menu size translation is unreliable (#417)")
    ap.add_argument("--policy", type=Path, default=Path("web/app/policy/mid-6.json"))
    ap.add_argument("--out", type=Path, default=None, help="write the full JSON here")
    a = ap.parse_args(argv)
    res = build(a.policy)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_bytes((json.dumps(res, separators=(",", ":")) + "\n").encode("utf-8"))
    print(table(res["summary"]))
    print(f"table lookups {res['table_lookups']}, missing (uniform) {res['table_missing']}; EV: {res['ev']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
