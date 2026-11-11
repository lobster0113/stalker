"""c1 LBR of a web policy file, as the page plays it (#653, follow-up 3 of the c1 web export note).

The page's AI seats act from `web/app/policy/<tier>-<n>.json` (rows already filtered by `min_visits`) and play uniformly
where the table has no row. ADR 0020's LBR line was measured on the table *before* that filter; this wraps the filtered
file as the policy object `referee.e3.lbr` reads (read-only import) and runs the same LBR on it.

    python -m stalker.tools.web_policy_lbr --policy mid-3.json --players 3 --hands 200 --seed 653 [--backoff] [--l4-neighbor]

A key the table lacks is uniform; with `--backoff` it is the row the page would play (`web_hit_rate.backoff_row`:
L1-L3, plus L4 with `--l4-neighbor`). Output is JSON without timings, so one seed gives the same bytes every run.
A local reference number; CI numbers are the ones that count.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.tools import web_hit_rate as H


class WebPolicy:
    """Callable policy for `referee.e3.lbr.seat_probs`: (key, legal actions) -> row, or None (= uniform)."""

    def __init__(self, table: dict, k: int, backoff: bool = False, l4: bool = False):
        self.table = table
        self.backoff = backoff or l4
        self.l4 = k - 1 if l4 else None
        self.tables = H.coarse_tables(table) if self.backoff else []

    def __call__(self, key: str, acts):
        m = len(acts)
        if self.backoff:
            return H.backoff_row(self.table, self.tables, key, m, self.l4)[0]
        return H._row(self.table, key, m)


def measure(path: Path, players: int, hands: int, seed: int, backoff: bool = False, l4: bool = False,
            aivat_samples: int = 0) -> dict:
    from referee.e3.lbr import exploitability_lb

    raw = Path(path).read_bytes()
    table, doc = H.load_policy(path)
    if doc.get("players") != players:
        raise SystemExit(f"{path}: file is for {doc.get('players')} players, not --players {players}; pass the file's count")
    variant = H.variant_of(table, doc)
    if (backoff or l4) and not variant:
        raise SystemExit("--backoff reads c1 keys only; a legacy table has no coarse-key levels")
    pol = WebPolicy(table, doc["k"], backoff, l4)
    rules = H.rules_of(doc)
    with G.rules(rules["menu"], rules["raise_cap"]), K.using_variant(variant):
        lb = exploitability_lb(pol, hands, seed=seed, k=doc["k"], n=players, depth=doc["depth"], aivat_samples=aivat_samples)
    return {"lbr_bb": lb["lbr_bb"], "lbr_stderr_bb": lb["stderr_bb"], "by_seat": lb["by_seat"], "hands": hands,
            "seed": seed, "players": players, "policy_sha256": hashlib.sha256(raw).hexdigest(),
            "backoff": bool(backoff or l4), "l4_neighbor": bool(l4),
            **{k: lb[k] for k in ("aivat_lbr_bb", "aivat_stderr_bb") if k in lb}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--policy", type=Path, required=True)
    ap.add_argument("--players", type=int, required=True)
    ap.add_argument("--hands", type=int, default=200, help="LBR hands per seat")
    ap.add_argument("--seed", type=int, default=653)
    ap.add_argument("--backoff", action="store_true", help="play a missing key by the page's L1-L3 backoff row")
    ap.add_argument("--l4-neighbor", action="store_true", help="also L4 (equity +-1 neighbour); implies --backoff")
    a = ap.parse_args(argv)
    json.dump(measure(a.policy, a.players, a.hands, a.seed, a.backoff, a.l4_neighbor), sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
