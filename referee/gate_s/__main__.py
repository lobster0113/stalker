"""python -m referee.gate_s [--env e1|e1m] [--tier T] [--scale S|--view V] [--out f.json] | --check: Gate S v0, JSON to stdout.

Default: evaluates the Nash anchor (must pass: the gate's own sanity check) and the E1 TP bottleneck
policy of the given tier. Exit code 1 if either fails.
--check (the `gates full` step, #287): the anchor must pass and the oversensitive and flattened
policies must fail; no TP policy is trained. TP policy results are record-only (CI metrics
`gate_s_e1`) until the GATES.md thresholds are settled.
--env e1m (#313): the same on 3-handed ICM push/fold (`referee.gate_s.e1m`), the TP policy of
`stalker.e1.multiway_pushfold` with --view; record-only, not in `gates full` or the CI metrics.
"""
import argparse
import json
import sys
from pathlib import Path

from referee import gate_s as S


def check() -> int:
    spec, _ = S.load()
    ok = True
    for name, pol, must_pass in (("nash_anchor", S.nash_policy, True), ("oversensitive", S.oversensitive_policy, False),
                                 ("flat", S.flat_policy, False)):
        r = S.evaluate(pol, spec)
        if r["passed"] != must_pass:
            ok = False
            print(f"Gate S check: {name} {'failed' if must_pass else 'passed'} "
                  f"({r['fails'] or 'no fails'}); the gate lost its discrimination - fix referee/gate_s before trusting it",
                  file=sys.stderr)
    return 0 if ok else 1


def e1m(a) -> int:
    from referee.gate_s import e1m as M

    spec, sha = M.load()
    pols = {"nash_anchor": M.nash_policy_for(spec)}
    if a.check:
        pols |= {"oversensitive": M.oversensitive_policy_for(spec), "flat": M.flat_policy_for(spec)}
    else:
        from stalker.e1.multiway_pushfold import gate_s_policy
        pols[f"e1m_tp_{a.tier}_{a.view}"] = gate_s_policy(a.view, a.tier, a.iters)
    res = {"env": "e1m", "spots": "e1m_v1", "sha256": sha, "policies": {k: M.evaluate(p, spec) for k, p in pols.items()}}
    text = json.dumps(res, indent=1)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
    for name, r in res["policies"].items():
        for f in r["fails"]:
            print(f"Gate S e1m [{name}] {f}", file=sys.stderr)
    if a.check:
        ok = res["policies"]["nash_anchor"]["passed"] and not any(res["policies"][k]["passed"] for k in ("oversensitive", "flat"))
        return 0 if ok else 1
    return 0 if all(r["passed"] for r in res["policies"].values()) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tier", default="beginner", choices=["beginner", "mid", "pro"])
    ap.add_argument("--scale", default="quantile", choices=["quantile", "uniform"])
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check", action="store_true", help="anchor passes and discrimination policies fail (gates full)")
    ap.add_argument("--env", default="e1", choices=["e1", "e1m"])
    ap.add_argument("--view", default="composite", choices=["rank", "strongest", "composite"], help="e1m pusher summary")
    ap.add_argument("--iters", type=int, default=1500, help="e1m TP policy training iterations per spot")
    a = ap.parse_args()
    if a.env == "e1m":
        return e1m(a)
    if a.check:
        return check()
    from stalker.e1.tp_pushfold import gate_s_policy

    spec, sha = S.load()
    res = {"spots": "v1", "sha256": sha,
           "policies": {"nash_anchor": S.evaluate(S.nash_policy, spec),
                        f"e1_tp_{a.tier}_{a.scale}": S.evaluate(gate_s_policy(a.tier, a.scale), spec)}}
    text = json.dumps(res, indent=1)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
    for name, r in res["policies"].items():
        for f in r["fails"]:
            print(f"Gate S [{name}] {f}", file=sys.stderr)
    return 0 if all(r["passed"] for r in res["policies"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
