"""`python -m referee.gate_r [--full] [--seeds N]`: per-item pass/total for tournaments and cash; exit 1 on any failure."""
from __future__ import annotations

import argparse
import sys

from referee.gate_r.cash_suite import FULL_HANDS, FULL_SESSIONS, QUICK_HANDS, QUICK_SESSIONS, run_cash_suite
from referee.gate_r.suite import run_suite


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m referee.gate_r")
    ap.add_argument("--full", action="store_true", help="include slow presets (mtt180) and 108k cash hands")
    ap.add_argument("--seeds", type=int, default=5, help="seeds per preset variant and bot")
    args = ap.parse_args(argv)
    tally = run_suite(args.seeds, args.full)
    cash, hands = run_cash_suite(*((FULL_SESSIONS, FULL_HANDS) if args.full else (QUICK_SESSIONS, QUICK_HANDS)))
    ok = _report("gate_r", tally, "fix the engine (stalker/tournament) or, if the rule itself is wrong, "
                 "referee/gate_r via referee-change")
    ok &= _report(f"gate_r_cash ({hands} hands x 2 engines)", cash,
                  "fix stalker/cash or the hand engines; engine_agreement names the first differing event")
    return 0 if ok else 1


def _report(title: str, tally, fix: str) -> bool:
    for item, (passed, total) in tally.counts.items():
        print(f"{item:18s} {passed}/{total}")
    print(f"{title}: {tally.passed}/{tally.total} ({tally.pass_rate:.4%})")
    if tally.passed == tally.total:
        return True
    print("failures (first {}):".format(len(tally.failures)))
    print("\n".join("  " + f for f in tally.failures))
    print(fix)
    return False


if __name__ == "__main__":
    sys.exit(main())
