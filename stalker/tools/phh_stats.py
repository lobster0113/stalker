"""Population stats (VPIP·PFR·3-bet·AF·WTSD·W$SD·flop c-bet) from PHH hand records (#519).

Flop c-bet and fold-to-flop-c-bet are also split into 4 cells (#627): heads-up | multiway (players
who saw the flop) x single-raised | 3-bet+ pot (preflop raises), because persona targets such as
TAG 65 are quoted for heads-up single-raised pots.

Used only to validate persona targets (docs/research/2026-10-30-population-stats.md) against public
data; the parser stays in referee/gate_r/phh.py (imported, not modified). Seat 1 is SB, seat 2 is BB
(PHH convention, same as the recorded blinds order). Pure function of the records -> deterministic.

    python -m stalker.tools.phh_stats [--json]
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict

from referee.gate_r.phh import load_sample

BOT = "Pluribus"
_KEYS = ("hands", "vpip", "pfr", "tb_opp", "tb", "bets", "calls", "flop", "wtsd", "showdowns",
         "sd_won", "cb_opp", "cb")
CELLS = ("hu_srp", "hu_3bp", "mw_srp", "mw_3bp")
_CELL_KEYS = tuple(f"{k}_{c}" for c in CELLS for k in ("cb_opp", "cb", "fcb_opp", "fcb"))
_ALL_KEYS = _KEYS + _CELL_KEYS


def hand_counts(rec: dict) -> dict[str, dict[str, int]]:
    """Per-player raw counters for one hand. Hands with fewer than 3 players give nothing."""
    names = rec["players"]
    n = len(names)
    out = {p: dict.fromkeys(_ALL_KEYS, 0) for p in names}
    if n < 3:
        return {}
    for p in names:
        out[p]["hands"] = 1
    alive = [True] * n
    committed = [0] * n
    committed[0], committed[1] = rec["blinds_or_straddles"][0], rec["blinds_or_straddles"][1]
    cur = committed[1]
    street = 0
    raises = 0
    pf_aggressor = -1
    vpip = [False] * n
    pfr = [False] * n
    tb_seen = [False] * n
    saw_flop = [False] * n
    flop_bet_made = False
    flop_acted = [False] * n
    cell = ""
    cbet_live = False  # a flop c-bet is the only bet so far: the next actors face it
    faced_cb = [False] * n
    for a in rec["actions"]:
        t = a.split()
        if t[0] == "d":
            if t[1] == "db":
                street += 1
                committed = [0] * n
                cur = 0
                if street == 1:
                    for i in range(n):
                        saw_flop[i] = alive[i]
                    cell = ("hu" if sum(alive) == 2 else "mw") + ("_srp" if raises == 1 else "_3bp")
            continue
        i = int(t[0][1:]) - 1
        c = out[names[i]]
        kind = t[1]
        if kind == "sm":  # card show at showdown, not a betting action
            continue
        if street == 0:
            if kind == "f":
                alive[i] = False
                if not tb_seen[i] and raises == 1:
                    tb_seen[i] = True
                    c["tb_opp"] += 1
            elif kind == "cc":
                if cur > committed[i]:
                    vpip[i] = True
                    if not tb_seen[i] and raises == 1:
                        tb_seen[i] = True
                        c["tb_opp"] += 1
                    committed[i] = cur
            else:
                vpip[i] = pfr[i] = True
                if not tb_seen[i] and raises == 1:
                    tb_seen[i] = True
                    c["tb_opp"] += 1
                    c["tb"] += 1
                raises += 1
                pf_aggressor = i
                cur = committed[i] = int(t[2])
        else:
            if kind == "f":
                alive[i] = False
            elif kind == "cc":
                if cur > committed[i]:
                    c["calls"] += 1
                    committed[i] = cur
            else:
                c["bets"] += 1
                cur = committed[i] = int(t[2])
            if street == 1:
                is_cb = False
                if i == pf_aggressor and not flop_acted[i] and not flop_bet_made:
                    is_cb = kind == "cbr"
                    c["cb_opp"] += 1
                    c["cb"] += is_cb
                    c[f"cb_opp_{cell}"] += 1
                    c[f"cb_{cell}"] += is_cb
                elif cbet_live and not faced_cb[i]:
                    faced_cb[i] = True
                    c[f"fcb_opp_{cell}"] += 1
                    c[f"fcb_{cell}"] += kind == "f"
                    if kind == "cbr":  # raised: later actors face a raise, not the c-bet
                        cbet_live = False
                if is_cb:
                    cbet_live = True
                flop_acted[i] = True
                flop_bet_made = flop_bet_made or kind == "cbr"
    n_alive = sum(alive)
    profit = [f - s for f, s in zip(rec["finishing_stacks"], rec["starting_stacks"])]
    for i, p in enumerate(names):
        c = out[p]
        c["vpip"], c["pfr"], c["flop"] = int(vpip[i]), int(pfr[i]), int(saw_flop[i])
        if saw_flop[i] and alive[i] and n_alive >= 2 and street >= 3:
            c["wtsd"] = 1
            c["showdowns"] = 1
            c["sd_won"] = int(profit[i] > 0)
    return out


def aggregate(recs: list[dict]) -> dict[str, dict[str, int]]:
    """Counters summed into `bot` (Pluribus seat) and `human` groups."""
    tot = {g: dict.fromkeys(_ALL_KEYS, 0) for g in ("bot", "human")}
    for rec in recs:
        for p, c in hand_counts(rec).items():
            g = tot["bot" if p == BOT else "human"]
            for k, v in c.items():
                g[k] += v
    return tot


def _pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


def rates(c: dict[str, int]) -> dict[str, float | None]:
    return {
        "hands": c["hands"],
        "VPIP": _pct(c["vpip"], c["hands"]),
        "PFR": _pct(c["pfr"], c["hands"]),
        "3bet": _pct(c["tb"], c["tb_opp"]),
        "AF": round(c["bets"] / c["calls"], 2) if c["calls"] else None,
        "WTSD": _pct(c["wtsd"], c["flop"]),
        "W$SD": _pct(c["sd_won"], c["showdowns"]),
        "flop_cbet": _pct(c["cb"], c["cb_opp"]),
        "3bet_opps": c["tb_opp"],
        "cbet_opps": c["cb_opp"],
        "showdowns": c["showdowns"],
    }


def _wilson(a: int, b: int) -> list[float] | None:
    """95% Wilson interval in percent; behaves at small b and rates near 0/100."""
    if not b:
        return None
    z = 1.959964
    p = a / b
    d = 1 + z * z / b
    mid = (p + z * z / (2 * b)) / d
    half = z * math.sqrt(p * (1 - p) / b + z * z / (4 * b * b)) / d
    return [round(100 * (mid - half), 1), round(100 * (mid + half), 1)]


def cell_rates(c: dict[str, int]) -> dict[str, dict]:
    """Flop c-bet and fold-to-flop-c-bet per cell, with opportunities and 95% intervals."""
    out = {}
    for cell in CELLS:
        cb, cbo = c[f"cb_{cell}"], c[f"cb_opp_{cell}"]
        f, fo = c[f"fcb_{cell}"], c[f"fcb_opp_{cell}"]
        out[cell] = {"cbet": _pct(cb, cbo), "cbet_opps": cbo, "cbet_ci95": _wilson(cb, cbo),
                     "fold_to_cbet": _pct(f, fo), "fold_opps": fo, "fold_ci95": _wilson(f, fo)}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    res = {g: {**rates(c), "cells": cell_rates(c)} for g, c in aggregate(load_sample()).items()}
    if args.json:
        print(json.dumps(res, indent=1, sort_keys=True))
    else:
        for g, r in res.items():
            print(g, r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
