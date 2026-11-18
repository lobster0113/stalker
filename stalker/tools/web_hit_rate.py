"""How often the browser's c1 policy table has a row for the actor's real hand (#611).

The page's AI seats act from `web/app/policy/<tier>-<n>.json` and play uniformly where the table has no row
(`tpgto.js actionProbs`). Seeded hands of the table's seat count are played with that rule through the engine
(`stalker.e3.game`) under the page's rules: the size menu and raise cap the file says it was trained on
(`rules_of`, as `tpgto.js menuOf`) and 100BB for every seat (the page deals `newHand` without stacks; #618 —
before it the hands ran on the v1 menu at sampled depths, so a real-menu table could not match a single
non-call key); at every decision the actor's real c1 key (`tp_key.key(public_key(variant="c1"), step)`) is
looked up. The output counts decisions and hits per street (0..3) and for call-or-fold `call|` keys. With a
checkpoint (`--pod-result`, as `export_web_players`) it also gives the same table for `min_visits` candidates:
a key hits when the table has it and the checkpoint saw it that often.

`--backoff` (#618) also asks, for every decision whose exact key misses, whether a coarser key would have found a
row: the table's rows are averaged per coarse key (`coarse_key`, levels `L1`, `L2`, `L3`; rows of a different length
are never merged), and each decision is counted at the first level that hits: exact -> L1 -> L2 -> L3 -> uniform. The play
itself keeps the old rule (a miss plays uniformly), so turning it off gives the old output unchanged.

`--play-backoff` (#635, implies `--backoff`) plays by the page's real rule instead (#623, `tpgto.js backoffRow`): an
exact miss acts from (and updates the ranges with) the first coarse level's mean row, uniform only when no level has
one. The trajectory is then the one the page makes; the output says `"play": "backoff"` (absent = uniform play, the
old output) and is schema_version 3.

`--miss-report N` (#638, needs `--play-backoff`) breaks down the decisions that stay uniform after the last level (L3
since #645, L2 before): per street the N most frequent last-level keys of those misses (count desc, key asc), and per
field position of that key (`call:<i>` for a
`call|` key) how many of them would hit if only that one field were `*` (`by_field`; `any_field` = at least one).
The play is unchanged; the output then carries `"miss_report"` and is schema_version 4.

`--l4-neighbor` (#648, implies `--backoff`; off by default) adds a level `L4` after L3: the L3 key with only its
equity field `e<n>` moved to `e<n-1>` and `e<n+1>` (steps outside `0..k-1` skipped); the L3 rows found there of the
same length are averaged (one found = that row). With `--play-backoff` the play uses it too, as the page does since
#652 (`tpgto.js backoffRow`); `--miss-report` then breaks down what is still uniform after L4. The output carries
`"l4_neighbor": true`, L4 in `by_backoff.levels` and is schema_version 5. Off, the output is the one without the flag, byte for byte.

`--fidelity` (#666, needs `--play-backoff`) weighs the backoff rows by what the page really plays: at every decision whose
exact key hits, that key's row is taken out of the coarse tables (`backoff_fidelity.loo_row`, mean combine, L4 as
`--l4-neighbor` says) and the first approximate level's row is set against the exact row, so a key that comes up often
counts as often. Output `"fidelity"`: street (0..3) -> level (L1..L3, L4, uniform) -> `n` decisions, `tv_mean`,
`uniform_tv_mean`, `argmax_agree`, `uniform_argmax_agree` (uniform counts 1/m; ties go to the smallest index). The play is
unchanged; the output is schema_version 6 and, without the flag, the one without it, byte for byte.

Every `by_backoff.by_street`/`by_kind` cell also carries `uniform_ci95` (#819): the 95% Wilson interval `[lo, hi]` of
its `uniform / decisions` share (fractions 0..1, six decimals, `null` at 0 decisions; `wilson.wilson95`), the upper
bound the uniform-share verdicts (#733, #805) are judged by, so they read it from the CI output.

    L1  drop the b1 hand items (`o<outs>v<vuln>k<block>`) and the stack depths (`s<mine>:<opps>` -> `s*`)
    L2  L1, and the public facts (`u<before><after>`, `h`, `g`) and the SPR step -> `*`; a `call|` key drops only
        its opponent count (it has no b1, stack or fact items)
    L3  L2, and the c1 position name -> its `tp_key.position_group` (early / late / blind) at that player count
        (#645); `call|` and beginner `b|` keys are as at L2 (no position name)

What stays at L2 is what the beginner key asks too (TP.md §4.1): position, players, street, opponents, raise count,
initiative, pot odds, the legal menu and the hand's equity step; L3 asks the position as the beginner key does (its
group).

    python -m stalker.tools.web_hit_rate web/app/policy/mid-3.json --hands 1000 --seed 611
    python -m stalker.tools.web_hit_rate web/app/policy/mid-3.json --pod-result result.json

Reference measurements only; CI numbers are the ones that count.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

from stalker.e2.eq_view import N
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.tools.wilson import wilson95

SCHEMA = "stalker.web.hit-rate"
SCHEMA_VERSION = 2   # 2: optional by_backoff (#618); a v1 output is the same without it. 3 = play_backoff (#635),
                     # 4 = 3 + miss_report (#638), 5 = l4_neighbor (#648), 6 = fidelity (#666); each is the previous output plus one block
# by_backoff cells' uniform_ci95 (#819) adds no version: readers ignore unknown fields and no reader keys on its absence
MIN_VISITS = (0, 1, 2, 5, 10)
LEVELS = ("L1", "L2", "L3")
_EQ = re.compile(r"e\d+")
_B1 = re.compile(r"o[\d-](v[\d-])?(k[\d-])?")
_STACK = re.compile(r"s\d+(:\d*)?")
_FACT = re.compile(r"u\d*|h[nmba]|g[nmxo]")
_SPR_AT = 7   # field index of the SPR step in a full-depth key (`tp_key.public_key`), after a pro `p|`


def position_group_of(name: str, players: str) -> str:
    """`tp_key.position_group` of the seat a c1 position name (`tp_key.C1_POSITIONS`) stands for at `n<players>`."""
    n = int(players[1:])
    return K.position_group(n, K.c1_position_names(n).index(name))


def coarse_key(key: str, level: int) -> str:
    """The key with the items of backoff `level` (1 = L1, 2 = L2, 3 = L3; module doc) dropped; level 0 is the key."""
    if level <= 0:
        return key
    parts = key.split("|")
    if parts[0] == "call":   # no position field: L3 = L2
        if level >= 2:
            parts[2] = "*"
        return "|".join(parts)
    at = max(i for i, f in enumerate(parts) if _EQ.fullmatch(f))
    head = ["s*" if _STACK.fullmatch(f) else f for f in parts[:at]]
    tail = [f for f in parts[at:] if not _B1.fullmatch(f)]
    if level >= 2:
        head = ["*" if _FACT.fullmatch(f) else f for f in head]
        if head[0] != "b":   # basic keys carry no SPR
            head[_SPR_AT + (head[0] == "p")] = "*"
    if level >= 3 and head[0] != "b":   # basic keys already carry the group
        at = int(head[0] == "p")
        head[at] = position_group_of(head[at], head[at + 1])
    return "|".join(head + tail)


def coarse_tables(policy: dict) -> list[dict]:
    """Per backoff level, coarse key -> {row length -> the mean of the table's rows with that coarse key}."""
    out = []
    for level in range(1, len(LEVELS) + 1):
        acc: dict = {}
        for k, row in policy.items():
            c = acc.setdefault(coarse_key(k, level), {}).setdefault(len(row), [np.zeros(len(row)), 0])
            c[0] += row
            c[1] += 1
        out.append({ck: {m: (tot / n).tolist() for m, (tot, n) in by_m.items()} for ck, by_m in acc.items()})
    return out


def neighbor_row(tables: list[dict], key: str, m: int, top: int):
    """L4 (module doc): the mean of the L3 rows of length m at the L3 key with its equity step moved by -1 and +1
    (steps outside 0..top skipped), None when neither has one."""
    parts = coarse_key(key, len(LEVELS)).split("|")
    at = max(i for i, f in enumerate(parts) if _EQ.fullmatch(f))
    step = int(parts[at][1:])
    rows = []
    for v in (step - 1, step + 1):
        if 0 <= v <= top:
            r = tables[len(LEVELS) - 1].get("|".join(parts[:at] + [f"e{v}"] + parts[at + 1:]), {}).get(m)
            if r is not None:
                rows.append(r)
    return np.mean(rows, axis=0).tolist() if rows else None


def backoff_level(policy: dict, tables: list[dict], key: str, m: int, l4: int | None = None) -> int:
    """0 = the exact key has a row, 1.. = the first coarse level with a row of length m, after the last level
    (L3, or L4 with `l4` = the top equity step) none. `l4=None` is the old lookup."""
    return backoff_row(policy, tables, key, m, l4)[1]


def backoff_row(policy: dict, tables: list[dict], key: str, m: int, l4: int | None = None):
    """(row, level) the page plays for `key` (`tpgto.js backoffRow`): the exact row (level 0), else the first coarse
    level's mean row, else (None, len(LEVELS)+1) = uniform. With `l4` (the top equity step, #648) L4's
    `neighbor_row` is tried after L3 and uniform is len(LEVELS)+2."""
    row = _row(policy, key, m)
    if row is not None:
        return row, 0
    for level, tab in enumerate(tables, 1):
        r = tab.get(coarse_key(key, level), {}).get(m)
        if r is not None:
            return r, level
    if l4 is None:
        return None, len(tables) + 1
    r = neighbor_row(tables, key, m, l4)
    return (r, len(tables) + 1) if r is not None else (None, len(tables) + 2)


def masked_index(tables: list[dict]) -> set:
    """(field position, last-level key with that field `*`, row length) for every last-level row: one-field-release lookups."""
    out = set()
    for ck, by_m in tables[len(LEVELS) - 1].items():
        parts = ck.split("|")
        for i in range(len(parts)):
            masked = "|".join(parts[:i] + ["*"] + parts[i + 1:])
            out.update((i, masked, m) for m in by_m)
    return out


def release_fields(index: set, key: str, m: int) -> list[int]:
    """Field positions of `key`'s last-level key that, set to `*` alone, find a last-level row of length m (fields already `*` skip)."""
    parts = coarse_key(key, len(LEVELS)).split("|")
    return [i for i, f in enumerate(parts) if f != "*"
            and (i, "|".join(parts[:i] + ["*"] + parts[i + 1:]), m) in index]


def _mcell() -> dict:
    return {"misses": 0, "keys": {}, "by_field": {}, "any_field": 0}


def _mreport(c: dict, top: int) -> dict:
    keys = sorted(c["keys"].items(), key=lambda kv: (-kv[1], kv[0]))[:top]
    by_field = dict(sorted(c["by_field"].items(), key=lambda kv: (-kv[1], kv[0])))
    return {"misses": c["misses"], "distinct_keys": len(c["keys"]), "top_keys": [list(kv) for kv in keys],
            "by_field": by_field, "any_field": c["any_field"]}


def _bcell(l4: bool = False) -> dict:
    return {"decisions": 0, "exact": 0, **{name: 0 for name in LEVELS}, **({"L4": 0} if l4 else {}), "uniform": 0}


def uniform_ci95(c: dict) -> list[float] | None:
    """95% Wilson interval of `uniform / decisions` (0..1, six decimals; None at 0 decisions) — the bound #733/#805 judge by (#819)."""
    ci = wilson95(c["uniform"], c["decisions"])
    return None if ci is None else [round(ci[0], 6), round(ci[1], 6)]


def _brate(c: dict) -> dict:
    n = c["decisions"]
    names = ("exact", *LEVELS, *(("L4",) if "L4" in c else ()), "uniform")
    return {**c, "rate": {k: (c[k] / n if n else None) for k in names}, "uniform_ci95": uniform_ci95(c)}


def load_policy(path: Path) -> tuple[dict, dict]:
    """A web policy file -> (key -> probability row, the file's header)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    q = doc["q"]
    return {k: [x / q for x in row] for k, row in doc["policy"].items()}, doc


def l1_extra_of(doc: dict) -> dict:
    """The file's optional `l1_rows` (#803: `export_web_players._top_fit` groups) as `measure`'s `l1_extra`:
    {L1 key: {row length: row}}. A file without the field gives {} (the page then builds L1 from the file alone)."""
    out: dict = {}
    for group, by_eq in (doc.get("l1_rows") or {}).items():
        parts = group.split("|")
        at = parts.index("e*")   # the one equity field `_group_of` wildcarded
        for step, v in by_eq.items():
            ck = "|".join([*parts[:at], "e" + step, *parts[at + 1:]])
            rows = v if v and isinstance(v[0], list) else [v]
            out[ck] = {len(r): r for r in rows}
    return out


def rules_of(doc: dict) -> dict:
    """The deal rules a policy file was trained on, read as `tpgto.js menuOf`: v1 with cap 3 when unsaid."""
    return {"menu": doc.get("menu") or "v1", "raise_cap": doc.get("raise_cap", G.RAISE_CAP)}


def _cell() -> dict:
    return {"decisions": 0, "hits": 0}


def _rate(c: dict) -> dict:
    return {**c, "rate": c["hits"] / c["decisions"] if c["decisions"] else None}


def _row(policy: dict, key: str, m: int):
    p = policy.get(key)
    return p if p is not None and len(p) == m else None


def measure(policy: dict, players: int, tier_k: int, depth: str, hands: int, seed: int,
            visits: dict | None = None, min_visits=MIN_VISITS, backoff: bool = False,
            rules: dict | None = None, variant: str = "c1", play_backoff: bool = False,
            miss_report: int = 0, l4_neighbor: bool = False, fidelity: bool = False,
            coarse_policy: dict | None = None, l1_extra: dict | None = None) -> dict:
    """Play `hands` seeded hands; the table's row (uniform when absent) drives every seat, as the page does.
    `rules`: `rules_of` the file (default v1, cap 3). `variant`: the key layout, "c1" or "" for a legacy table (#620; the page's `decisionKey` variant). `backoff`: also count the first level (module doc) whose coarse table has the actor's row (`by_backoff`). `play_backoff`: act by `backoff_row` instead of uniform on a miss (module doc; implies `backoff`). `fidelity`: the play-weighted leave-one-out quality of the backoff rows (module doc; needs `play_backoff`). `miss_report`: the top-N last-level miss breakdown (module doc; needs `play_backoff`). `l4_neighbor`: the L4 equity-neighbor level (module doc; implies `backoff`). `coarse_policy`: build the backoff tables (L1-L3) from this table instead of `policy`; exact lookups stay on `policy` (#743: a table from before the visit threshold keeps L1 material the threshold erased). None = `policy`. `l1_extra`: {L1 key: {row length: row}} added to the first backoff level where the table has no row of that (key, length) (#790: rows a page would ship beside the file)."""
    if miss_report and not play_backoff:
        raise ValueError("miss_report needs play_backoff (#638)")
    if fidelity and not play_backoff:
        raise ValueError("fidelity needs play_backoff (#666)")
    if fidelity:
        from stalker.tools import backoff_fidelity as BF   # it imports this module
        sums = BF.sum_tables(policy)
        fid: dict = {str(st): {} for st in range(4)}
    backoff = backoff or play_backoff or l4_neighbor
    l4 = tier_k - 1 if l4_neighbor else None
    rng = np.random.default_rng([seed, 611, players])
    by_street = {str(st): _cell() for st in range(4)}
    kinds = {"call": _cell(), "other": _cell()}
    cand = {str(v): {"street": {str(st): _cell() for st in range(4)}, "call": _cell(), "other": _cell()}
            for v in min_visits} if visits is not None else {}
    tables = coarse_tables(policy if coarse_policy is None else coarse_policy) if backoff else []
    if tables:
        for ck, by_m in (l1_extra or {}).items():
            for m, row in by_m.items():
                tables[0].setdefault(ck, {}).setdefault(m, row)
    names = ("exact", *LEVELS, *(("L4",) if l4_neighbor else ()), "uniform")
    b_street = {str(st): _bcell(l4_neighbor) for st in range(4)}
    b_kind = {"call": _bcell(l4_neighbor), "other": _bcell(l4_neighbor)}
    index = masked_index(tables) if miss_report else set()
    m_street = {str(st): _mcell() for st in range(4)}
    for _ in range(hands):
        s = G.deal(rng, players, **(rules or {}))
        ranges = K.initial_ranges(players)
        while not s.done:
            acts, p = G.legal(s), s.to_act
            m = len(acts)
            public = K.public_key(s, p, depth, variant=variant)
            steps = K.equity_steps(s, p, ranges, tier_k, variant=variant)
            real = K.key(public, K.my_step(steps, s, p))
            hit = _row(policy, real, m) is not None
            kind = "call" if public.startswith("call|") else "other"
            by_street[str(s.street)]["decisions"] += 1
            by_street[str(s.street)]["hits"] += int(hit)
            kinds[kind]["decisions"] += 1
            kinds[kind]["hits"] += int(hit)
            for v, tab in cand.items():
                h = hit and visits.get(real, 0) >= int(v)
                for c in (tab["street"][str(s.street)], tab[kind]):
                    c["decisions"] += 1
                    c["hits"] += int(h)
            if fidelity and hit:
                approx, lname = BF.loo_row(sums, real, policy[real], tier_k - 1 if l4_neighbor else None)
                exact = policy[real]
                agree = 1.0 / m if lname == "uniform" else float(np.argmax(approx) == np.argmax(exact))
                f = fid[str(s.street)].setdefault(lname, [0, 0.0, 0.0, 0.0, 0.0])
                f[0] += 1
                f[1] += BF.tv(exact, approx)
                f[2] += BF.tv(exact, np.full(m, 1.0 / m))
                f[3] += agree
                f[4] += 1.0 / m
            if backoff:
                level = names[backoff_level(policy, tables, real, m, l4)]
                for c in (b_street[str(s.street)], b_kind[kind]):
                    c["decisions"] += 1
                    c[level] += 1
                if miss_report and level == "uniform":
                    mc = m_street[str(s.street)]
                    ck = coarse_key(real, len(LEVELS))
                    mc["misses"] += 1
                    mc["keys"][ck] = mc["keys"].get(ck, 0) + 1
                    rel = release_fields(index, real, m)
                    mc["any_field"] += int(bool(rel))
                    for i in rel:
                        name = f"call:{i}" if kind == "call" else str(i)
                        mc["by_field"][name] = mc["by_field"].get(name, 0) + 1
            # Dead combos (step -1) weigh 0, as the page's seatProbs; np.empty left them as stale memory (NaN at
            # times), which changed the ranges and so the run with the process's memory layout (#644).
            probs = np.zeros((N, m))
            for v in np.unique(steps[steps >= 0]):
                k = K.key(public, int(v))
                row = backoff_row(policy, tables, k, m, l4)[0] if play_backoff else _row(policy, k, m)
                probs[steps == v] = row if row is not None else np.full(m, 1.0 / m)
            real_row = backoff_row(policy, tables, real, m, l4)[0] if play_backoff else _row(policy, real, m)
            pr = np.asarray(real_row if real_row is not None else np.full(m, 1.0 / m), dtype=float)
            i = int(rng.choice(m, p=pr / pr.sum()))
            ranges = K.update_range(ranges, p, probs[:, i])
            s = G.apply(s, acts[i])
    version = 6 if fidelity else 5 if l4_neighbor else 4 if miss_report else 3 if play_backoff else SCHEMA_VERSION
    out = {"schema": SCHEMA, "schema_version": version, "players": players, "hands": hands, "seed": seed,
           "by_street": {k: _rate(c) for k, c in by_street.items()},
           "by_kind": {k: _rate(c) for k, c in kinds.items()}}
    if play_backoff:
        out["play"] = "backoff"
    if l4_neighbor:
        out["l4_neighbor"] = True
    if visits is not None:
        out["by_min_visits"] = {v: {"by_street": {k: _rate(c) for k, c in t["street"].items()},
                                    "by_kind": {k: _rate(t[k]) for k in ("call", "other")}} for v, t in cand.items()}
    if backoff:
        out["by_backoff"] = {"levels": list(names), "keys": {"exact": len(policy), **{
                                 name: sum(len(by_m) for by_m in tab.values()) for name, tab in zip(LEVELS, tables)}},
                             "by_street": {k: _brate(c) for k, c in b_street.items()},
                             "by_kind": {k: _brate(c) for k, c in b_kind.items()}}
    if fidelity:
        out["fidelity"] = {st: {lv: {"n": f[0], "tv_mean": round(f[1] / f[0], 6), "uniform_tv_mean": round(f[2] / f[0], 6),
                                     "argmax_agree": round(f[3] / f[0], 6), "uniform_argmax_agree": round(f[4] / f[0], 6)}
                                for lv, f in sorted(by.items())} for st, by in fid.items()}
    if miss_report:
        out["miss_report"] = {"top": miss_report,
                              "by_street": {k: _mreport(c, miss_report) for k, c in m_street.items()}}
    return out


def variant_of(policy: dict, doc: dict, choice: str = "auto") -> str:
    """The key layout of a table: `--variant` if given, else the header's `key_variant`, else read off the first key
    (c1 keys carry `|n<players>`; the pre-c1 keys are bare numbers; `call|` keys are the same in both, so skipped, #620)."""
    if choice != "auto":
        return "" if choice == "legacy" else choice
    if "key_variant" in doc:
        return doc["key_variant"]
    first = next((k for k in policy if not k.startswith("call|")), None)
    return "c1" if first is None or "|n" in first else ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("policy", type=Path, help="web/app/policy/<tier>-<n>.json")
    ap.add_argument("--hands", type=int, default=200)
    ap.add_argument("--seed", type=int, default=611)
    ap.add_argument("--backoff", action="store_true",
                    help="also count where coarser keys (L1, L2, L3) would find a row (#618, #645)")
    ap.add_argument("--play-backoff", action="store_true",
                    help="play by the page's backoff rule, not uniform, on an exact miss; implies --backoff (#635)")
    ap.add_argument("--miss-report", type=int, default=0, metavar="N",
                    help="top-N last-level (L3) keys still uniform and the one-field releases that would hit; needs --play-backoff (#638)")
    ap.add_argument("--l4-neighbor", action="store_true",
                    help="after L3, try the L3 rows one equity step either side (L4, #648); implies --backoff")
    ap.add_argument("--fidelity", action="store_true",
                    help="play-weighted leave-one-out quality of the backoff rows at exact hits; needs --play-backoff (#666)")
    ap.add_argument("--coarse-policy", type=Path, metavar="FILE",
                    help="build the backoff tables (L1-L3) from this policy file; exact lookups stay on the main file (#743)")
    ap.add_argument("--variant", choices=("auto", "c1", "legacy"), default="auto",
                    help="key layout; auto = the file's key_variant, else read off its first key (#620)")
    ap.add_argument("--pod-result", type=Path, help="the training result holding the visit counts (min_visits table)")
    a = ap.parse_args(argv)
    if a.miss_report and not a.play_backoff:
        raise SystemExit("--miss-report needs --play-backoff: it breaks down the misses of the page's backoff play (#638)")
    if a.fidelity and not a.play_backoff:
        raise SystemExit("--fidelity needs --play-backoff: it weighs the rows by the page's backoff trajectory (#666)")
    if a.miss_report < 0:
        raise SystemExit("--miss-report N: N must be >= 1 (0 = off)")
    policy, doc = load_policy(a.policy)
    variant = variant_of(policy, doc, a.variant)
    if variant not in ("", "c1"):
        raise SystemExit(f"{a.policy}: key variant {variant!r}; this tool reads c1 and legacy keys only")
    if (a.backoff or a.play_backoff or a.l4_neighbor) and not variant:
        raise SystemExit("--backoff/--play-backoff read c1 keys only; a legacy table has no coarse-key levels (#620)")
    visits = None
    if a.pod_result:
        from stalker.tools import export_web_policy as X

        st, _ = X.load_pod_result(a.pod_result)
        visits = dict(X.load_model(st).visits)
    coarse = load_policy(a.coarse_policy)[0] if a.coarse_policy else None
    res = measure(policy, doc["players"], doc["k"], doc["depth"], a.hands, a.seed, visits, backoff=a.backoff,
                  play_backoff=a.play_backoff, rules=rules_of(doc), variant=variant, miss_report=a.miss_report,
                  l4_neighbor=a.l4_neighbor, fidelity=a.fidelity, coarse_policy=coarse,
                  l1_extra=l1_extra_of(doc) or None)
    json.dump({**res, "variant": variant or "legacy", "file": a.policy.name}, sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
