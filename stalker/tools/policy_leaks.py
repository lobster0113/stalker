"""Known preflop leaks of a served policy, for the page's warnings (#441): `python -m stalker.tools.policy_leaks`.

The served tier policies are training intermediates with a known preflop defect (#391): the #413 probe
(`python -m referee.e3.preflop_probe <policy> --json probe.json`) finds cells (spot, seat, hand group)
where one first action beats the policy's own mix by a large, Bonferroni-significant margin. Until the
retrain (#426) fixes them, the page must not grade the hero against those rows. This tool turns a probe
result into a small file next to the policy, `web/app/policy/<tier>-6.leaks.json`, that lists every
measured cell (so the page can tell "measured, no leak" from "not measured") and the leak details.

Two stages, both pre-registered (#441). The screen is one probe run over every cell; its Bonferroni family
is the whole grid (hundreds of tests), so at a few hundred deals per cell it misses real leaks. The
confirmation re-probes, with more deals and an independent seed, only the screened cells whose best
deviation already clears the threshold with an uncorrected 95% lower bound above zero, and corrects for
that smaller family alone. A cell is a leak when either stage flags it (family-wise error <= 2 x alpha).

    python -m referee.e3.preflop_probe web/app/policy/mid-6.json --deals 300 --seed 0 --workers 3 --json mid.probe.json
    python -m stalker.tools.policy_leaks --tier mid --screen mid.probe.json --save-confirm mid.confirm.json --workers 3 \
        --out web/app/policy/mid-6.leaks.json --evidence "local; CI test covers mid HJ/CO AA"

The numbers are as good as the run that made them; a local run is a reference value (CLAUDE.md), and
`evidence` says where they came from.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from referee.e3 import preflop_probe as P

SCHEMA = "stalker.web.policy-leaks"
SCHEMA_VERSION = 1
PROBE = "e3_preflop_v1"
TIERS = ("beginner", "mid", "pro")
# The page keys a decision by engine seat (0 = UTG ... n-1 = BB, web/app/tpgto.js positionNames).
POSITIONS = {6: ("UTG", "HJ", "CO", "BTN", "SB", "BB")}
CONFIRM_DEALS = 1000
CONFIRM_SEED = 7


def candidates(screen: dict) -> list[dict]:
    """Screened cells the confirmation re-probes: not yet a leak, best gain above the threshold, uncorrected
    95% lower bound above zero."""
    out = []
    for c in screen["cells"]:
        b = c.get("best")
        if b is None or c.get("leak"):
            continue
        x = c["actions"][b]
        if x["vs_row_bb"] > screen["threshold_bb"] and x["vs_row_ci"][0] > 0:
            out.append(c)
    return out


def confirm(table: dict, screen: dict, deals: int = CONFIRM_DEALS, seed: int = CONFIRM_SEED, workers: int = 1) -> dict:
    """Re-probe the candidates (one probe call per cell, each with its own seed) and flag them as one family."""
    pos = POSITIONS[screen["players"]]
    cells = []
    for i, c in enumerate(candidates(screen)):
        r = P.probe(table, deals, seed * 100_000 + i, (c["spot"],), [pos.index(c["seat"])], (c["group"],), workers)
        cells += r["cells"]
    z = P.flag(cells, screen["threshold_bb"])
    return {"probe": PROBE, "stage": "confirm", "deals_per_cell": deals, "seed": seed,
            "threshold_bb": screen["threshold_bb"], "alpha": P.ALPHA, "z_corrected": round(z, 3),
            "players": screen["players"], "menu": screen.get("menu"), "cells": cells,
            "leaks": sum(c["leak"] for c in cells)}


def _r(x, nd: int = 2):
    return None if x is None else round(float(x), nd)


def build(probe: dict, tier: str, policy_file: str, policy_meta: dict | None = None,
          evidence: str = "local", command: str | None = None, confirmed: dict | None = None) -> dict:
    """The leaks file for one tier from a screen probe result (`referee.e3.preflop_probe ... --json`) and,
    optionally, its confirmation (`confirm`); a cell the confirmation flags reports the confirmation's numbers."""
    for d in (probe, confirmed or {"probe": PROBE}):
        if d.get("probe") != PROBE:
            raise ValueError(f"probe {d.get('probe')!r}: expected a {PROBE} result from "
                             "python -m referee.e3.preflop_probe <policy> --json <out>")
    if tier not in TIERS:
        raise ValueError(f"tier {tier!r}; known: {TIERS}")
    n = probe["players"]
    if n not in POSITIONS:
        raise ValueError(f"{n} players: the page keys leak cells for 6-max tables only")
    seat_of = {p: i for i, p in enumerate(POSITIONS[n])}
    cells, leaks, spots, seats, groups = [], [], [], [], []
    again = {(c["spot"], c["seat"], c["group"]): c for c in (confirmed or {}).get("cells", [])}
    for c0 in probe["cells"]:
        c2 = again.get((c0["spot"], c0["seat"], c0["group"]))
        c, stage = (c2, "confirm") if c2 is not None and c2.get("leak") else (c0, "screen")
        seat = seat_of[c["seat"]]
        for lst, v in ((spots, c["spot"]), (seats, c["seat"]), (groups, c["group"])):
            if v not in lst:
                lst.append(v)
        measured = bool(c.get("actions"))
        cells.append({"spot": c["spot"], "seat": seat, "pos": c["seat"], "group": c["group"], "deals": c["deals"],
                      "measured": measured, "leak": bool(c.get("leak")), "confirmed": c2 is not None})
        if not c.get("leak"):
            continue
        b = c["best"]
        x = c["actions"][b]
        leaks.append({
            "spot": c["spot"], "seat": seat, "pos": c["seat"], "group": c["group"], "deals": c["deals"], "stage": stage,
            "best": b, "gain_bb": _r(x["vs_row_bb"]), "gain_ci": [_r(v) for v in x["vs_row_ci"]],
            "gain_low_bb": _r(c.get("leak_low_bb")),
            "row": {a: _r(v["row"], 3) for a, v in c["actions"].items()},
            "open_minus_limp": {a: {"bb": _r(v["bb"]), "ci": [_r(u) for u in v["ci"]]}
                                for a, v in (c.get("open_minus_limp") or {}).items()},
        })
    meta = policy_meta or {}
    return {
        "schema": SCHEMA, "schema_version": SCHEMA_VERSION, "tier": tier, "players": n,
        "policy": policy_file, "policy_run_id": meta.get("run_id"), "policy_sha": meta.get("sha"),
        "issue": 391, "probe": PROBE, "evidence": evidence, "command": command,
        "settings": {"deals_per_cell": probe["deals_per_cell"], "seed": probe["seed"], "spots": spots,
                     "seats": seats, "groups": groups, "threshold_bb": probe["threshold_bb"],
                     "alpha": probe["alpha"], "z_corrected": probe["z_corrected"], "menu": probe.get("menu"),
                     "confirm": None if confirmed is None else {
                         "rule": "screened, not a leak, best gain > threshold and uncorrected 95% lower bound > 0",
                         "cells": len(confirmed["cells"]), "deals_per_cell": confirmed["deals_per_cell"],
                         "seed": confirmed["seed"], "z_corrected": confirmed["z_corrected"]}},
        "cells": cells, "leaks": leaks,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="probe result (#413) -> web/app/policy/<tier>-6.leaks.json (#441)")
    ap.add_argument("--screen", "--probe", dest="probe", type=Path, required=True,
                    help="screen: JSON written by referee.e3.preflop_probe --json")
    ap.add_argument("--confirm", type=Path, default=None, help="a saved confirmation (skips re-probing)")
    ap.add_argument("--save-confirm", type=Path, default=None, help="run the confirmation and save it here")
    ap.add_argument("--confirm-deals", type=int, default=CONFIRM_DEALS)
    ap.add_argument("--confirm-seed", type=int, default=CONFIRM_SEED)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--tier", required=True, choices=TIERS)
    ap.add_argument("--policy", type=Path, default=None,
                    help="the probed policy file (default web/app/policy/<tier>-6.json); its run id goes in the meta")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--evidence", default="local", help="where the numbers come from, e.g. 'local; CI test covers mid HJ/CO AA'")
    ap.add_argument("--command", default=None, help="the probe command line, kept in the file so the run can be repeated")
    a = ap.parse_args(argv)
    policy = a.policy or Path("web/app/policy") / f"{a.tier}-6.json"
    meta = None
    if policy.exists():
        d = json.loads(policy.read_text(encoding="utf-8"))
        meta = {k: d.get(k) for k in ("run_id", "sha")}
    screen = json.loads(a.probe.read_text(encoding="utf-8"))
    conf = None
    if a.confirm:
        conf = json.loads(a.confirm.read_text(encoding="utf-8"))
    elif a.save_confirm:
        conf = confirm(P.load(policy), screen, a.confirm_deals, a.confirm_seed, a.workers)
        a.save_confirm.write_text(json.dumps(conf, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(P.table(conf))
    try:
        out = build(screen, a.tier, policy.name, meta, a.evidence, a.command, conf)
    except (ValueError, KeyError) as e:
        print(f"policy_leaks: {e}", file=sys.stderr)
        return 1
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{a.out}: {len(out['leaks'])} leak cells of {len(out['cells'])} measured ({a.tier})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
