"""Test vectors for the browser port of the E3 TP-GTO lookup (web/app/tpgto.js, #335).

Per (players, tier) a tiny E3MCCFR is trained for a few iterations so its regret-matching policy is
not uniform, then seeded random hands are played from `G.deal`. Every decision records what the
browser must reproduce exactly: legal actions, public key, the actor's equity-step array (1326
combos), key, and each seat's range sum after the Bayes update with the policy (uniform where the
table has no entry, as `E3MCCFR._sigma`). The policy rows the hands look up are included, so the JS
test needs nothing else. Also written: numpy runout draws (`default_rng([20261028, *board])`) to
test the RNG port alone, and the 169-class preflop table as web/app/assets/hu_equity.json.

`menus` (#386): seeded random hands under the wider size menus (real with and without the postflop cap,
tp6, and v1 as served) at 2, 6 and 9 players. Per decision: legal actions, every size's street total, the public key at
each depth and, when the actor bets an arbitrary amount (min raise, any amount, an exact menu size, all
in), the translation split (stalker/e3/translate.split), the seeded reading
(translate.sample with default_rng([seed, hand, decision])) and the high-translation-error flag
(translate.high_translation_error, #417). `hte` (#417): that flag on every 0.1BB size at fixed lines
(HTE_LINES) where each branch of the rule fires. Equity steps do not depend on the menu, so
these hands carry none.

    python -m stalker.tools.web_vectors            # rewrite web/app/test/vectors.json and the asset
    node --test web/app/test/                     # check the JS port against them
"""
from __future__ import annotations

import argparse
import json
import re
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
SCHEMA_VERSION = 5   # 2: "menus" block (#386); 3: v1 menu hands and the per-bet "hte" flag (#417); 4: "c1_keys" (#583);
# 5: "b1" (#606)
TIERS = ("beginner", "mid", "pro")
PLAYERS = (2, 4, 6, 9)   # 2 and 4: the web looks up per-seat policies (#541)
FOLD_WEIGHTS = (0.15, 1.0, 4.0)   # per hand: deep multiway hands, plain random, fold-heavy (heads-up postflop)
DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
MENU_RULES = (("real", None), ("real", 3), ("tp6", 3), ("v1", 3))   # (menu, raise_cap); real + None is the training job;
# v1 (the served tables) is last so the earlier blocks keep their seeds
MENU_PLAYERS = (2, 6, 9)
DEPTHS = ("basic", "full", "pro")
C1_PLAYERS = (2, 4, 6)   # ADR 0021: the short-handed counts the mixn c1 policy serves
C1_HANDS = 10


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
            d.update(bet=to, split=[[a, f] for a, f in X.split(s, to)], entropy=entropy, read=read,
                     hte=X.high_translation_error(s, to))
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


# Fixed lines for the high-translation-error rule (#417): every 0.1BB from the min raise to all in at
# spots where each branch of the rule fires (v1 open and 3-bet: the all-in neighbour; v1 flop: b33|b75,
# the gap rule; real: the all-in above the top size; short stacks: the ALLIN_MERGE exemption).
HTE_LINES = (("v1", 3, 100, ()), ("v1", 3, 100, ("f", "f", "r")), ("v1", 3, 100, ("f", "f", "f", "r", "f", "c")),
             ("v1", 3, 15, ("f", "f", "f")), ("real", None, 100, ()), ("real", None, 100, ("f", "f", "r")),
             ("real", None, 100, ("f", "f", "f", "r", "f", "c")), ("tp6", 3, 100, ("f", "f", "f", "r", "f", "c")))


def hte_vectors(seed: int) -> list[dict]:
    out = []
    for i, (menu, cap, stack_bb, line) in enumerate(HTE_LINES):
        s = G.deal(np.random.default_rng([seed, 417, i]), 6, menu, cap)
        perm = [c for hl in s.hole for c in hl] + list(s.deck)
        s = s._replace(stack=tuple(stack_bb * G.BB - b for b in s.bet))
        for a in line:
            s = G.apply(s, a)
        p = s.to_act
        room = s.stack[p] + s.bet[p]
        least = min(max(s.bet) + s.last_raise, room)
        cases = [[to, X.high_translation_error(s, to)]
                 for to in sorted({least, room} | set(range(-(-least // 10) * 10, room + 1, 10)))]
        out.append({"menu": menu, "raise_cap": cap, "stack_bb": stack_bb, "perm": perm, "line": list(line),
                    "cases": cases})
    return out


def _play_c1(n: int, rng: np.random.Generator) -> dict:
    # One 20-250BB depth per hand (the browser engine has no side pots yet, so no mixed stacks) so the stack field
    # takes several values; seeded random actions (folds and all ins damped).
    stacks = G.sample_stacks(rng, n, equal_p=1.0)
    s = G.deal(rng, n, stacks=stacks)
    perm = [c for hl in s.hole for c in hl] + list(s.deck)
    decisions = []
    while not s.done:
        acts, p = G.legal(s), s.to_act
        pub = [K.public_key(s, p, depth, variant="c1") for depth in DEPTHS]
        wts = np.array([0.4 if a == "f" else 0.05 if a == "a" else 1.0 for a in acts])
        a = acts[int(rng.choice(len(acts), p=wts / wts.sum()))]
        decisions.append({"a": a, "legal": acts, "public": pub})
        s = G.apply(s, a)
    return {"n": n, "stacks": list(stacks), "perm": perm, "decisions": decisions}


def c1_vectors(hands: int, seed: int) -> dict:
    """c1 public keys (#583, ADR 0021): the web mirrors `tp_key.public_key(variant="c1")` string for string.
    The equity step and the b1 draw label after it are not mirrored here (a later issue)."""
    out = []
    for n in C1_PLAYERS:
        rng = np.random.default_rng([seed, 583, n])
        out.extend(_play_c1(n, rng) for _ in range(hands))
    return {"version": K.KEY_VERSIONS["c1"], "positions": {str(n): list(K.c1_position_names(n)) for n in C1_PLAYERS},
            "hands": out}


# b1 vectors (#606): the ranges must not stay uniform (every opponent alike would hide an order or weight bug), but
# shipping 1326 floats per update is heavy, so each update multiplies the actor's range by a factor both sides compute
# from (combo, update id) with exact integer arithmetic (< 2^53 in JS).
B1_FACTORS = (1.0, 0.8, 0.5, 0.25, 0.05, 0.0)
B1_PLAYERS = (2, 3, 6)   # heads-up, the smallest multiway table, and 6-max flops with 3+ live players
B1_HANDS = 4
B1_DIGITS = 2            # base-36 digits per code: codes are < B1_RADIX**3 = 216 < 36**2


def b1_factor_index(i: int, u: int) -> int:
    return (i * 2654435761 + u * 40503 + 12345) % 4294967296 // 128 % len(B1_FACTORS)


def b1_update(ranges: list[np.ndarray], seat: int, u: int) -> list[np.ndarray]:
    f = np.array([B1_FACTORS[b1_factor_index(i, u)] for i in range(N)])
    return K.update_range(ranges, seat, f)


def _encode_codes(codes: np.ndarray) -> str:
    return "".join(DIGITS[int(c) // 36] + DIGITS[int(c) % 36] for c in codes)


def _play_b1(n: int, h: int, rng: np.random.Generator) -> dict:
    s = G.deal(rng, n)
    perm = [c for hl in s.hole for c in hl] + list(s.deck)
    ranges = K.initial_ranges(n)
    decisions = []
    while not s.done:
        acts, p = G.legal(s), s.to_act
        d = {"u": h * 100 + len(decisions)}
        if s.street > 0:
            full = K.b1_code(s, p, ranges, "full")
            basic = K.b1_code(s, p, ranges, "basic")
            d.update(street=s.street, live=len(s.live()), full=_encode_codes(full), basic=_encode_codes(basic),
                     labels={str(int(c)): K.b1_label(int(c)) for c in sorted(set(full.tolist()) | set(basic.tolist()))})
        # Few folds so 6-max flops stay multiway; all ins rare so later streets are reached.
        wts = np.array([0.15 if a == "f" else 0.03 if a == "a" else 1.0 for a in acts])
        d["a"] = acts[int(rng.choice(len(acts), p=wts / wts.sum()))]
        ranges = b1_update(ranges, p, d["u"])
        decisions.append(d)
        s = G.apply(s, d["a"])
    return {"n": n, "perm": perm, "decisions": decisions}


def b1_vectors(hands: int, seed: int, players=B1_PLAYERS) -> dict:
    """tp_key.b1_code at full and basic depth for every combo of the actor, at every postflop decision, and
    b1_label of every code that occurs (#606): the web port must match them exactly."""
    out = []
    for n in players:   # seeded per player count, so a subset rebuilds the same hands
        rng = np.random.default_rng([seed, 606, n])
        out.extend(_play_b1(n, 100 * n + j, rng) for j in range(hands))
    return {"factors": list(B1_FACTORS), "radix": K.B1_RADIX, "na": K.B1_NA, "none": K.B1_NONE,
            "edges": {"outs": list(K.OUTS_EDGES), "vuln": list(K.VULN_EDGES), "block": list(K.BLOCK_EDGES)},
            "out_gain": K.OUT_GAIN, "hands": out}


def b1_parts(b1: dict) -> dict:
    """How many postflop decisions each case the test needs has: heads-up, multiway, per street."""
    ds = [(h, d) for h in b1["hands"] for d in h["decisions"] if "full" in d]
    return {"decisions": len(ds), "heads_up": sum(1 for _, d in ds if d["live"] == 2),
            "multiway": sum(1 for _, d in ds if d["live"] >= 3),
            "by_street": {st: sum(1 for _, d in ds if d["street"] == st) for st in (1, 2, 3)},
            "six_max_multiway": sum(1 for h, d in ds if h["n"] == 6 and d["live"] >= 3)}


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
            "menus": menu_vectors(menu_hands, seed), "hte": hte_vectors(seed),
            "c1_keys": c1_vectors(C1_HANDS, seed), "b1": b1_vectors(B1_HANDS, seed)}


def c1_parts(v: dict) -> dict:
    """Per player count, how many c1 decisions carry each key element (full depth): the test needs each at least once."""
    pats = {"players": r"\|n(\d)\|", "u": r"\|u\d\d\|", "stack": r"\|s\d:\d+\|", "g": r"\|g[nmxo]\|", "pos": None}
    out = {}
    for n in C1_PLAYERS:
        names = set(K.c1_position_names(n))
        ds = [d["public"][1] for h in v.get("c1_keys", {}).get("hands", ()) if h["n"] == n for d in h["decisions"]
              if not d["public"][1].startswith("call|")]
        c = {k: sum(1 for x in ds if re.search(r, x)) for k, r in pats.items() if r}
        c["players"] = sum(1 for x in ds if f"|n{n}|" in x)
        c["pos"] = sum(1 for x in ds if x.split("|")[0] in names)
        out[n] = c
    return out


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
            "menu_bets_split": sum(1 for h in v["menus"] for d in h["decisions"] if len(d.get("split", ())) == 2),
            "c1_hands": {n: sum(1 for h in v.get("c1_keys", {}).get("hands", ()) if h["n"] == n) for n in C1_PLAYERS},
            "c1_parts": c1_parts(v),
            "hte_cases": sum(len(x["cases"]) for x in v.get("hte", ())),
            "hte_flagged": sum(f for x in v.get("hte", ()) for _, f in x["cases"]),
            "menu_bets_hte": sum(1 for h in v["menus"] for d in h["decisions"] if d.get("hte")),
            "menu_bets_hte_gap": sum(1 for h in v["menus"] for d in h["decisions"]
                                     if d.get("hte") and d["split"][1][0] != "a")}


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
