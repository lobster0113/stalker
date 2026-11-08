"""How close the page's backoff rows (L1-L4, `web_hit_rate.backoff_row`) are to the rows they stand in for (#654).

#645 and #648 measured only how often a coarse level finds a row. Here every exact key `k` of a c1 table is treated
as if it were missing: each level's coarse table is rebuilt without `k`'s own row (the mean of the other rows of the
same length under that coarse key; none left = that level misses), and the first level that has a row, in the
page's order L1 -> L2 -> L3 -> [L4] -> uniform, is `k`'s approximation. Its total variation distance to `k`'s real
row, TV = 1/2 sum |p - q|, is set against the TV of the uniform row for the same key. L4 (`--l4-neighbor`) averages
the L3 rows one equity step either side; those coarse keys differ from `k`'s own L3 key in the equity field, so
`k`'s row is never in them and no exclusion is needed.

`--combine mode` (#660) tests the guess that the mean of near-pure rows is close to uniform: instead of the mean,
a level's approximation is the mean of only those rows whose argmax is the coarse cell's most common argmax (ties,
both inside a row and between actions, go to the smallest action index). L4 takes each neighbour's mode row the
same way and combines those again by the same rule.

Output (schema_version 2): per street (`call|` keys apart, under `call_keys`) and per level the key count `n`,
`tv_mean`, `tv_p90`, the same keys' `uniform_tv_mean` and `better_than_uniform` (share of keys whose approximation
is strictly closer than uniform), `argmax_agree` (share of keys whose approximation's argmax is the real row's
argmax; a uniform approximation counts 1/m, its chance of agreeing under a random pick) and `uniform_argmax_agree`
(mean 1/m), plus top-level `combine`. With `--combine mean` the schema 1 fields keep their values. Keys are walked
sorted and numbers rounded to 6 places, so the same table gives the same bytes.

    python -m stalker.tools.backoff_fidelity web/app/policy/mid-3.json --l4-neighbor [--combine mode]

Reference measurements only; CI numbers are the ones that count.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from stalker.tools.web_hit_rate import LEVELS, _EQ, coarse_key, load_policy, variant_of

SCHEMA = "stalker.web.backoff-fidelity"
SCHEMA_VERSION = 2
COMBINES = ("mean", "mode")


def street_of(key: str) -> int:
    """The street field of a c1 key: `call|<st>|..`, `b|n<n>|<group>|<st>|..`, `[p|]<pos>|n<n>|<st>|..`."""
    parts = key.split("|")
    if parts[0] == "call":
        return int(parts[1])
    return int(parts[3] if parts[0] in ("b", "p") else parts[2])


def sum_tables(policy: dict) -> list[dict]:
    """Per level, coarse key -> {row length -> [row sum, row count]} (sums, so one row can be taken back out)."""
    out = []
    for level in range(1, len(LEVELS) + 1):
        acc: dict = {}
        for k in sorted(policy):
            row = np.asarray(policy[k], dtype=float)
            c = acc.setdefault(coarse_key(k, level), {}).setdefault(len(row), [np.zeros(len(row)), 0])
            c[0] += row
            c[1] += 1
        out.append(acc)
    return out


def mode_tables(policy: dict) -> list[dict]:
    """Per level, coarse key -> {row length -> (argmax counts, per-argmax row sums)} for `--combine mode`."""
    out = []
    for level in range(1, len(LEVELS) + 1):
        acc: dict = {}
        for k in sorted(policy):
            row = np.asarray(policy[k], dtype=float)
            m = len(row)
            cnt, sm = acc.setdefault(coarse_key(k, level), {}).setdefault(m, (np.zeros(m, dtype=int), np.zeros((m, m))))
            a = int(np.argmax(row))
            cnt[a] += 1
            sm[a] += row
        out.append(acc)
    return out


def mode_row(rows) -> np.ndarray | None:
    """Mean of the rows whose argmax is the most common argmax among `rows` (ties -> smallest index)."""
    rows = [np.asarray(r, dtype=float) for r in rows]
    if not rows:
        return None
    arg = [int(np.argmax(r)) for r in rows]
    best = int(np.argmax(np.bincount(arg, minlength=len(rows[0]))))
    return np.mean([r for r, a in zip(rows, arg) if a == best], axis=0)


def _mode_of(cnt, sm, row=None):
    """The cell's mode row, with `row` (the key's own) taken back out first; None if no row is left."""
    cnt = cnt.copy()
    sm = sm.copy()
    if row is not None:
        a = int(np.argmax(row))
        cnt[a] -= 1
        sm[a] -= row
    if cnt.sum() == 0:
        return None
    best = int(np.argmax(cnt))
    return sm[best] / cnt[best]


def _neighbor(sums: list[dict], key: str, m: int, top: int, combine: str = "mean"):
    """`web_hit_rate.neighbor_row` on the sum tables: mean of the L3 means at equity step -1 / +1 (in 0..top).
    With `combine="mode"` (`sums` from `mode_tables`) each neighbour's mode row, combined by `mode_row`."""
    parts = coarse_key(key, len(LEVELS)).split("|")
    at = max(i for i, f in enumerate(parts) if _EQ.fullmatch(f))
    step = int(parts[at][1:])
    rows = []
    for v in (step - 1, step + 1):
        if 0 <= v <= top:
            c = sums[len(LEVELS) - 1].get("|".join(parts[:at] + [f"e{v}"] + parts[at + 1:]), {}).get(m)
            if c is not None:
                rows.append(c[0] / c[1] if combine == "mean" else _mode_of(*c))
    if not rows:
        return None
    return np.mean(rows, axis=0) if combine == "mean" else mode_row(rows)


def loo_row(sums: list[dict], key: str, row, l4: int | None = None):
    """(approximate row, level name) the page would play if `key` (with real `row`) were missing from the table."""
    r = np.asarray(row, dtype=float)
    m = len(r)
    for name, level, tab in zip(LEVELS, range(1, len(LEVELS) + 1), sums):
        c = tab.get(coarse_key(key, level), {}).get(m)
        if c is not None and c[1] > 1:
            return (c[0] - r) / (c[1] - 1), name
    if l4 is not None:
        nb = _neighbor(sums, key, m, l4)
        if nb is not None:
            return nb, "L4"
    return np.full(m, 1.0 / m), "uniform"


def loo_mode_row(modes: list[dict], key: str, row, l4: int | None = None):
    """`loo_row` with `--combine mode`: `modes` from `mode_tables`."""
    r = np.asarray(row, dtype=float)
    m = len(r)
    for name, level, tab in zip(LEVELS, range(1, len(LEVELS) + 1), modes):
        c = tab.get(coarse_key(key, level), {}).get(m)
        if c is not None:
            approx = _mode_of(*c, row=r)
            if approx is not None:
                return approx, name
    if l4 is not None:
        nb = _neighbor(modes, key, m, l4, "mode")
        if nb is not None:
            return nb, "L4"
    return np.full(m, 1.0 / m), "uniform"


def tv(p, q) -> float:
    return 0.5 * float(np.abs(np.asarray(p, dtype=float) - np.asarray(q, dtype=float)).sum())


def _summary(cells: list[tuple[float, float, float, float]]) -> dict:
    """cells: (tv, uniform tv, argmax agreement 0/1 or 1/m, 1/m) per key."""
    a, u, g, gu = (np.array([c[i] for c in cells]) for i in range(4))
    return {"n": len(cells), "tv_mean": round(float(a.mean()), 6), "tv_p90": round(float(np.percentile(a, 90)), 6),
            "uniform_tv_mean": round(float(u.mean()), 6), "better_than_uniform": round(float((a < u).mean()), 6),
            "argmax_agree": round(float(g.mean()), 6), "uniform_argmax_agree": round(float(gu.mean()), 6)}


def _group(cells: dict) -> dict:
    """{street: {level: [(tv, uniform tv)]}} -> the same with each list summarised (empty cells left out)."""
    return {st: {lv: _summary(c) for lv, c in by.items() if c} for st, by in sorted(cells.items())}


def measure(policy: dict, top: int, l4_neighbor: bool = False, combine: str = "mean") -> dict:
    """Leave-one-out fidelity of every exact key (module doc). `top`: the highest equity step (the file's k - 1)."""
    if combine not in COMBINES:
        raise ValueError(f"combine {combine!r}: use one of {COMBINES}")
    tabs, approx_of = (sum_tables(policy), loo_row) if combine == "mean" else (mode_tables(policy), loo_mode_row)
    l4 = top if l4_neighbor else None
    names = (*LEVELS, *(("L4",) if l4_neighbor else ()), "uniform")
    cells: dict = {"other": {}, "call": {}}
    for k in sorted(policy):
        row = policy[k]
        approx, level = approx_of(tabs, k, row, l4)
        m = len(row)
        u = tv(row, np.full(m, 1.0 / m))
        agree = 1.0 / m if level == "uniform" else float(np.argmax(approx) == np.argmax(row))
        kind = "call" if k.startswith("call|") else "other"
        by = cells[kind].setdefault(str(street_of(k)), {n: [] for n in names})
        by[level].append((tv(row, approx), u, agree, 1.0 / m))
    out = {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, "combine": combine, "levels": list(names), "keys": len(policy),
           "by_street": _group(cells["other"]), "call_keys": {"by_street": _group(cells["call"])}}
    if l4_neighbor:
        out["l4_neighbor"] = True
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("policy", type=Path, help="web/app/policy/<tier>-<n>.json (a c1 table)")
    ap.add_argument("--l4-neighbor", action="store_true", help="try L4 (L3 rows one equity step either side) after L3 (#648)")
    ap.add_argument("--combine", choices=COMBINES, default="mean",
                    help="how a coarse cell's rows make one row: mean (the page's rule) or mode (#660)")
    a = ap.parse_args(argv)
    policy, doc = load_policy(a.policy)
    variant = variant_of(policy, doc)
    if variant != "c1":
        raise SystemExit(f"{a.policy}: key variant {variant or 'legacy'!r}; backoff levels exist only for c1 keys "
                         "(#620) — pass a c1 table (key_variant \"c1\", e.g. web/app/policy/mid-3.json)")
    res = measure(policy, doc["k"] - 1, a.l4_neighbor, a.combine)
    json.dump({**res, "file": a.policy.name, "players": doc["players"]}, sys.stdout, indent=1, sort_keys=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
