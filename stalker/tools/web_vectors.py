"""Test vectors for the browser port of the E3 TP-GTO lookup (web/app/tpgto.js, #335).

Per (players, tier) a tiny E3MCCFR is trained for a few iterations so its regret-matching policy is
not uniform, then seeded random hands are played from `G.deal`. Every decision records what the
browser must reproduce exactly: legal actions, public key, the actor's equity-step array (1326
combos), key, and each seat's range sum after the Bayes update with the policy (uniform where the
table has no entry, as `E3MCCFR._sigma`). The policy rows the hands look up are included, so the JS
test needs nothing else. Also written: numpy runout draws (`default_rng([20261028, *board])`) to
test the RNG port alone, and the 169-class preflop table as web/app/assets/hu_equity.json.

`menus` (#386): seeded random hands under the wider size menus (real with and without the postflop cap,
tp6) at 2, 6 and 9 players. Per decision: legal actions, every size's street total, the public key at
each depth and, when the actor bets an arbitrary amount (min raise, any amount, an exact menu size, all
in), the translation split (stalker/e3/translate.split) and the seeded reading
(translate.sample with default_rng([seed, hand, decision])). Equity steps do not depend on the menu, so
these hands carry none.

    python -m stalker.tools.web_vectors            # rewrite web/app/test/vectors.json and the asset
    node --test web/app/test/                     # check the JS port against them
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from referee.anchors.hu_equity import load as load_hu_equity
from stalker.core.cards import HAND_CLASSES
from stalker.e2.eq_view import EQ_RUNOUTS, N
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3 import translate as X
from stalker.e3.mccfr import E3MCCFR

ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "web" / "app" / "test" / "vectors.json"
ASSET = ROOT / "web" / "app" / "assets" / "hu_equity.json"
SCHEMA = "stalker.web.tpgto.vectors"
SCHEMA_VERSION = 2   # 2: "menus" block (#386)
TIERS = ("beginner", "mid", "pro")
PLAYERS = (6, 9)
FOLD_WEIGHTS = (0.15, 1.0, 4.0)   # per hand: deep multiway hands, plain random, fold-heavy (heads-up postflop)
DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
MENU_RULES = (("real", None), ("real", 3), ("tp6", 3))   # (menu, raise_cap); real + None is the training job
MENU_PLAYERS = (2, 6, 9)
DEPTHS = ("basic", "full", "pro")


def equity_table() -> dict:
    E, Np = load_hu_equity()
    return {"classes": HAND_CLASSES, "equity": E.tolist(), "pairs": Np.astype(int).tolist()}


def _seat_probs(policy: dict, public: str, steps: np.ndarray, m: int) -> np.ndarray:
    # As E3MCCFR._seat_probs with `_sigma` read from an exported table.
    out = np.zeros((N, m))
    for v in np.unique(steps[steps >= 0]):
        p = policy.get(K.key(public, int(v)))
        out[steps == v] = p if p is not None and len(p) == m else np.full(m, 1.0 / m)
    return out


def _seq_sum(a: np.ndarray) -> float:
    s = 0.0
    for v in a.tolist():
        s += v
    return s


def _encode_steps(steps: np.ndarray) -> tuple[str, int | None]:
    nut = None
    if steps.max() >= K.NUT_BASE:
        nuts = {int(v) // K.NUT_BASE - 1 for v in steps[steps >= 0]}
        assert len(nuts) == 1, nuts
        nut = nuts.pop()
    return "".join("-" if v < 0 else DIGITS[int(v) % K.NUT_BASE] for v in steps), nut


def _play(policy: dict, n: int, tier: str, rng: np.random.Generator, fold_w: float, used: dict) -> dict:
    k, depth = K.TIER_K[tier], K.TIER_DEPTH[tier]
    s = G.deal(rng, n)
    perm = [c for h in s.hole for c in h] + list(s.deck)  # the permutation G.deal drew
    ranges = K.initial_ranges(n)
    decisions = []
    while not s.done:
        acts = G.legal(s)
        p = s.to_act
        steps = K.equity_steps(s, p, ranges, k)
        public = K.public_key(s, p, depth)
        key = K.key(public, K.my_step(steps, s, p))
        probs = _seat_probs(policy, public, steps, len(acts))
        for v in np.unique(steps[steps >= 0]):
            kk = K.key(public, int(v))
            if kk in policy:
                used[kk] = policy[kk]
        wts = np.array([fold_w if a == "f" else 0.05 if a == "a" else 1.0 for a in acts])
        i = int(rng.choice(len(acts), p=wts / wts.sum()))
        ranges = K.update_range(ranges, p, probs[:, i])
        enc, nut = _encode_steps(steps)
        decisions.append({"a": acts[i], "legal": acts, "public": public, "steps": enc, "nut": nut, "key": key,
                          "sums": [_seq_sum(r) for r in ranges]})
        s = G.apply(s, acts[i])
    return {"n": n, "tier": tier, "perm": perm, "decisions": decisions,
            "board": list(s.board), "payoff": [int(x) for x in G.payoff(s)]}


def _bet_to(s: G.State, rng: np.random.Generator) -> int:
    # Min raise, any amount, an exact menu size or all in, so every branch of the translation is hit.
    p = s.to_act
    room = s.stack[p] + s.bet[p]
    least = min(max(s.bet) + s.last_raise, room)
    u = rng.random()
    if u < 0.2:
        return least
    if u < 0.35:
        menu = [t for _, t in G._offered(s)] or [room]
        return int(menu[int(rng.integers(len(menu)))])
    if u < 0.45:
        return room
    return int(rng.integers(least, room + 1))


def _play_menu(menu: str, cap, n: int, seed: int, h: int, rng: np.random.Generator) -> dict:
    s = G.deal(rng, n, menu, cap)
    perm = [c for hl in s.hole for c in hl] + list(s.deck)
    decisions = []
    while not s.done:
        acts, p = G.legal(s), s.to_act
        d = {"legal": acts, "amounts": {a: G._amount_to(s, a) for a in acts if a not in ("f", "c", "k")},
             "public": [K.public_key(s, p, depth) for depth in DEPTHS]}
        if any(a not in ("f", "c", "k") for a in acts) and rng.random() < 0.5:
            to = _bet_to(s, rng)
            entropy = [seed, h, len(decisions)]
            read = X.sample(s, to, np.random.default_rng(entropy))
            d.update(bet=to, split=[[a, f] for a, f in X.split(s, to)], entropy=entropy, read=read)
            s = G._advance(G._put_in(s, to, f"{p}:{read}"), p)   # chips by `to`, history by the reading
        else:
            wts = np.array([0.3 if a == "f" else 0.1 if a == "a" else 1.0 for a in acts])
            d["a"] = acts[int(rng.choice(len(acts), p=wts / wts.sum()))]
            s = G.apply(s, d["a"])
        decisions.append(d)
    return {"menu": menu, "raise_cap": cap, "n": n, "perm": perm, "decisions": decisions,
            "history": list(s.history), "board": list(s.board), "payoff": [int(x) for x in G.payoff(s)]}


def menu_vectors(hands: int, seed: int) -> list[dict]:
    out = []
    for r, (menu, cap) in enumerate(MENU_RULES):
        for n in MENU_PLAYERS:
            rng = np.random.default_rng([seed, 386, r, n])
            out.extend(_play_menu(menu, cap, n, seed, len(out), rng) for _ in range(hands))
    return out


def rng_vectors(count: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    out = []
    for t in range(count):
        board = [int(c) for c in rng.permutation(52)[:3 + t % 2]]
        r = np.random.default_rng([20261028, *board])
        live = np.array([c for c in range(52) if c not in board])
        out.append({"board": board, "runouts": [[int(x) for x in r.choice(live, size=5 - len(board), replace=False)]
                                                for _ in range(EQ_RUNOUTS)]})
    return out


def build(hands: int = 12, iters: int = 20, seed: int = 335, players=PLAYERS, tiers=TIERS, rng_count: int = 60,
          menu_hands: int = 10) -> dict:
    out_hands, policy_used = [], {}
    for n in players:
        for tier in tiers:
            m = E3MCCFR(seed, K.TIER_K[tier], n, K.TIER_DEPTH[tier])
            m.iterate(iters)
            policy = m.current_policy()
            rng = np.random.default_rng([seed, n, TIERS.index(tier)])  # a subset rebuilds the same hands
            for h in range(hands):
                out_hands.append(_play(policy, n, tier, rng, FOLD_WEIGHTS[h % len(FOLD_WEIGHTS)], policy_used.setdefault(f"{n}/{tier}", {})))
    return {"schema": SCHEMA, "schema_version": SCHEMA_VERSION,
            "constants": {"TIER_K": K.TIER_K, "TIER_DEPTH": K.TIER_DEPTH, "NUT_BASE": K.NUT_BASE, "NUT_TOP": K.NUT_TOP,
                          "NUT_K": K.NUT_K, "EQ_RUNOUTS": EQ_RUNOUTS},
            "params": {"hands": hands, "iters": iters, "seed": seed},
            "policies": policy_used, "hands": out_hands, "rng": rng_vectors(rng_count, seed),
            "menus": menu_vectors(menu_hands, seed)}


def summary(v: dict) -> dict:
    ds = [(h, d) for h in v["hands"] for d in h["decisions"]]
    return {"hands": len(v["hands"]), "decisions": len(ds),
            "by_street": {st: sum(1 for _, d in ds if d["public"].split("|")[2 if d["public"][0] in "bp" else 1] == st)
                          for st in "0123"},
            "call_keys": sum(1 for _, d in ds if d["public"].startswith("call|")),
            "board_nut": sum(1 for _, d in ds if d["nut"] is not None),
            "by_n": {n: sum(1 for h, _ in ds if h["n"] == n) for n in PLAYERS},
            "by_tier": {t: sum(1 for h, _ in ds if h["tier"] == t) for t in TIERS},
            "menu_decisions": sum(len(h["decisions"]) for h in v["menus"]),
            "menu_bets": sum(1 for h in v["menus"] for d in h["decisions"] if "bet" in d),
            "menu_bets_split": sum(1 for h in v["menus"] for d in h["decisions"] if len(d.get("split", ())) == 2)}


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write web/app TP-GTO test vectors and the preflop equity asset")
    ap.add_argument("--hands", type=int, default=12, help="hands per (players, tier)")
    ap.add_argument("--iters", type=int, default=20, help="MCCFR iterations per (players, tier)")
    ap.add_argument("--seed", type=int, default=335)
    ap.add_argument("--out", type=Path, default=VECTORS)
    ap.add_argument("--asset", type=Path, default=ASSET)
    a = ap.parse_args(argv)
    v = build(a.hands, a.iters, a.seed)
    _write(a.out, v)
    _write(a.asset, equity_table())
    print(json.dumps(summary(v)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
