"""TexasSolver throughput benchmark: `python -m stalker.tools.bench_texassolver [--accuracy 1 0.5 0.3]`.

Solves fixed heads-up single-raised-pot spots (river, turn, flop; same ranges, one bet size per street)
at each target exploitability and prints one JSON object per line per solve (stdout), keys `OUTPUT_FIELDS`:

- `street`: "river" | "turn" | "flop"
- `target_accuracy_pct`: requested exploitability target, % of pot (`--accuracy`)
- `threads`: solver thread count actually used
- `exploitability_pct`: last logged exploitability, % of pot (null if the solver wrote no log)
- `iterations`: iterations run (null if no log)
- `wall_s`: solve wall time in seconds, 2 decimals
- `peak_rss_mb`: solver process peak RSS in MB, 1 decimal
- `spots_per_day`: 86400 / `wall_s` on this machine with this thread count
- `solver_version`: installed commit from `<home>/VERSION` (null if missing)

#8-B uploads these lines as a CI artifact; changing the keys means updating that job and #8-C's table.
Needs `scripts/install_texassolver.sh`; exits 2 without the binary. Numbers are reference-only unless
produced by CI.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from stalker.oracle.texassolver import SolveResult, SolveSettings, Spot, StreetSizes, find_binary, solve

# Public sample ranges from the TexasSolver README (BTN open vs BB call, roughly).
RANGE_OOP = ("AA,KK,QQ,JJ,TT,99:0.75,88:0.75,77:0.5,66:0.25,55:0.25,AK,AQs,AQo:0.75,AJs,AJo:0.5,ATs:0.75,"
             "A6s:0.25,A5s:0.75,A4s:0.75,A3s:0.5,A2s:0.5,KQs,KQo:0.5,KJs,KTs:0.75,K5s:0.25,K4s:0.25,QJs:0.75,"
             "QTs:0.75,Q9s:0.5,JTs:0.75,J9s:0.75,J8s:0.75,T9s:0.75,T8s:0.75,T7s:0.75,98s:0.75,97s:0.75,96s:0.5,"
             "87s:0.75,86s:0.5,85s:0.5,76s:0.75,75s:0.5,65s:0.75,64s:0.5,54s:0.75,53s:0.5,43s:0.5")
RANGE_IP = ("QQ:0.5,JJ:0.75,TT,99,88,77,66,55,44,33,22,AKo:0.25,AQs,AQo:0.75,AJs,AJo:0.75,ATs,ATo:0.75,A9s,A8s,"
            "A7s,A6s,A5s,A4s,A3s,A2s,KQ,KJ,KTs,KTo:0.5,K9s,K8s,K7s,K6s,K5s,K4s:0.5,K3s:0.5,K2s:0.5,QJ,QTs,Q9s,"
            "Q8s,Q7s,JTs,JTo:0.5,J9s,J8s,T9s,T8s,T7s,98s,97s,96s,87s,86s,76s,75s,65s,64s,54s,53s,43s")
OUTPUT_FIELDS = ("street", "target_accuracy_pct", "threads", "exploitability_pct", "iterations", "wall_s",
                 "peak_rss_mb", "spots_per_day", "solver_version")
BOARDS = {"river": "Qs Jh 2h 8d 3c", "turn": "Qs Jh 2h 8d", "flop": "Qs Jh 2h"}


def spot_sizes() -> dict[tuple[str, str], StreetSizes]:
    one = StreetSizes(bet=(66,), raise_=(100,), allin=True)
    return {(p, s): one for p in ("oop", "ip") for s in ("flop", "turn", "river")}


def make_spot(street: str) -> Spot:
    return Spot(BOARDS[street], pot=10, effective_stack=95, range_oop=RANGE_OOP, range_ip=RANGE_IP,
                sizes=spot_sizes())


def result_line(street: str, accuracy: float, threads: int, r: SolveResult) -> dict:
    return {
        "street": street, "target_accuracy_pct": accuracy, "threads": threads,
        "exploitability_pct": r.exploitability, "iterations": r.iterations,
        "wall_s": round(r.wall_s, 2), "peak_rss_mb": round(r.peak_rss_mb, 1),
        # A fake or instant solve can report 0 s; keep the line valid JSON instead of dividing by zero.
        "spots_per_day": round(86400 / r.wall_s, 1) if r.wall_s > 0 else None,
        "solver_version": r.solver_version,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--streets", nargs="+", default=["river", "turn", "flop"], choices=list(BOARDS))
    ap.add_argument("--accuracy", nargs="+", type=float, default=[1.0, 0.5, 0.3])
    ap.add_argument("--max-iteration", type=int, default=300)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--timeout", type=float, default=3600)
    args = ap.parse_args(argv)
    if find_binary() is None:
        print("bench_texassolver: console_solver not found — run scripts/install_texassolver.sh", file=sys.stderr)
        return 2
    threads = args.threads or os.cpu_count() or 1
    for street in args.streets:
        for acc in args.accuracy:
            settings = SolveSettings(accuracy=acc, max_iteration=args.max_iteration, threads=threads)
            r = solve(make_spot(street), settings, timeout=args.timeout)
            print(json.dumps(result_line(street, acc, threads, r)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
