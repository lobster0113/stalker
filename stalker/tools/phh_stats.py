"""Population stats (VPIP·PFR·3-bet·AF·WTSD·W$SD·flop c-bet) from PHH hand records (#519).

Used only to validate persona targets (docs/research/2026-10-30-population-stats.md) against public
data; the parser stays in referee/gate_r/phh.py (imported, not modified). Seat 1 is SB, seat 2 is BB
(PHH convention, same as the recorded blinds order). Pure function of the records -> deterministic.

    python -m stalker.tools.phh_stats [--json]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

from referee.gate_r.phh import load_sample

BOT = "Pluribus"
_KEYS = ("hands", "vpip", "pfr", "tb_opp", "tb", "bets", "calls", "flop", "wtsd", "showdowns",
         "sd_won", "cb_opp", "cb")


def hand_counts(rec: dict) -> dict[str, dict[str, int]]:
    """Per-player raw counters for one hand. Hands with fewer than 3 players give nothing."""
    names = rec["players"]
    n = len(names)
    out = {p: dict.fromkeys(_KEYS, 0) for p in names}
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
                if i == pf_aggressor and not flop_acted[i] and not flop_bet_made:
                    c["cb_opp"] += 1
                    c["cb"] += kind == "cbr"
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
    tot = {g: dict.fromkeys(_KEYS, 0) for g in ("bot", "human")}
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    res = {g: rates(c) for g, c in aggregate(load_sample()).items()}
    if args.json:
        print(json.dumps(res, indent=1, sort_keys=True))
    else:
        for g, r in res.items():
            print(g, r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
