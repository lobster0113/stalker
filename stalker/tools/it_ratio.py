"""Ratio of per-iteration speed between two ops training summaries, overall and per shared CPU model (#527).

    python -m stalker.tools.it_ratio A.json B.json [--json]

Ratio is A/B. CPU assignment on shared runners is noisy (+-40%), so compare per CPU model when possible.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict


def _by_cpu(s: dict) -> dict[str, float]:
    rates, cpus = s.get("iters_per_s_by_seed"), s.get("cpu_model_by_seed")
    if not rates or not cpus or len(rates) != len(cpus):
        return {}
    acc: dict[str, list[float]] = defaultdict(list)
    for r, c in zip(rates, cpus):
        acc[c].append(r)
    return {c: sum(v) / len(v) for c, v in acc.items()}


def compare(a: dict, b: dict) -> dict:
    ma, mb = a.get("iters_per_s_mean"), b.get("iters_per_s_mean")
    out: dict = {"overall": {"a": ma, "b": mb, "ratio": round(ma / mb, 3) if ma and mb else None}}
    ca, cb = _by_cpu(a), _by_cpu(b)
    shared = sorted(set(ca) & set(cb))
    out["by_cpu"] = {c: {"a": round(ca[c], 3), "b": round(cb[c], 3), "ratio": round(ca[c] / cb[c], 3)} for c in shared}
    out["common_cpu"] = bool(shared)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)
    res = compare(*(json.load(open(p, encoding="utf-8")) for p in (ns.a, ns.b)))
    if ns.json:
        print(json.dumps(res, indent=2))
        return 0
    o = res["overall"]
    print(f"overall: {o['a']} / {o['b']} = {o['ratio']}")
    if not res["common_cpu"]:
        print("no common CPU model (old format or disjoint runners): per-CPU ratio unavailable")
    for c, v in res["by_cpu"].items():
        print(f"{c}: {v['a']} / {v['b']} = {v['ratio']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
