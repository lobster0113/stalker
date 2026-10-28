"""python -m referee.gate_s.threshold_table: the ADR 0016 table (pass/fail of the E1 policies per TP-change rule).

Local reference values (1500 CFR iterations per spot, fixed spot-set seed); trains 6 policies (~8 min).
"""
from referee import gate_s as S
from stalker.e1.tp_pushfold import TIER_STEP, gate_s_policy

RULES = {"A one step (v0)": lambda pts, step: pts <= step,
         "B fixed 10 points": lambda pts, step: pts <= 10,
         "C max(one step, 10 points)": lambda pts, step: pts <= max(step, 10)}


def main() -> None:
    spec = S.load()[0]
    rows = []
    for name, pol in (("nash_anchor", S.nash_policy), ("oversensitive", S.oversensitive_policy), ("flat", S.flat_policy)):
        r = S.evaluate(pol, spec)
        rows.append((name, None, r))
    for scale in ("quantile", "uniform"):
        for tier in ("beginner", "mid", "pro"):
            rows.append((f"{tier} {scale}", TIER_STEP[tier], S.evaluate(gate_s_policy(tier, scale), spec)))
    print("| policy | TP change p95 (steps / points) | other criteria | " + " | ".join(RULES) + " |")
    print("|---|---|---|" + "---|" * len(RULES))
    for name, step, r in rows:
        other = [f for f in r["fails"] if not f.startswith("tp change")]
        tp = "-" if step is None else f"{r['tp_change_p95']:g} / {r['tp_change_p95_points']:g}"
        cells = ["pass" if not other and (step is None or ok(r["tp_change_p95_points"], step)) else "fail"
                 for ok in RULES.values()]
        print(f"| {name} | {tp} | {'ok' if not other else f'fail ({len(other)})'} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
