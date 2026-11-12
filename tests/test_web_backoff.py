"""The page's c1 miss backoff (#623, ADR 0022) is the measurement tool's: tpgto.js `coarseKey`/`coarseTables`
give the same strings and mean rows as `stalker.tools.web_hit_rate.coarse_key`/`coarse_tables`."""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.tools import web_hit_rate as H

ROOT = Path(__file__).resolve().parent.parent
TPGTO = (ROOT / "web" / "app" / "tpgto.js").as_uri()
MID3 = ROOT / "web" / "app" / "policy" / "mid-3.json"

# Reads {"keys": [...], "table": {key: row}} on stdin; prints every coarse level of every key and the coarse tables.
_NODE = """
import * as T from %s;
let src = ""; process.stdin.on("data", (c) => (src += c)); process.stdin.on("end", () => {
  const { keys, table } = JSON.parse(src);
  const tabs = T.coarseTables(new Map(Object.entries(table).map(([k, r]) => [k, Float64Array.from(r)])));
  const out = tabs.map((t) => Object.fromEntries([...t].map(([ck, byM]) => [ck, Object.fromEntries([...byM].map(([m, r]) => [m, Array.from(r)]))])));
  process.stdout.write(JSON.stringify({ coarse: keys.map((k) => T.BACKOFF_LEVELS.map((_, l) => T.coarseKey(k, l + 1))), tables: out }));
});
"""


def _seeded_keys(depth: str, tier: str, players: int, hands: int, seed: int) -> list[str]:
    """c1 keys of every decision (all combos' steps, so b1 labels vary) of seeded hands with seeded random play."""
    rng = np.random.default_rng([seed, 623, players])
    out = set()
    for _ in range(hands):
        s = G.deal(rng, players, menu="real", raise_cap=None)
        ranges = K.initial_ranges(players)
        while not s.done:
            acts, p = G.legal(s), s.to_act
            pub = K.public_key(s, p, depth, variant="c1")
            steps = K.equity_steps(s, p, ranges, K.TIER_K[tier], variant="c1")
            for v in np.unique(steps[steps >= 0])[:6]:
                out.add(K.key(pub, int(v)))
            # Mostly passive so hands reach the river; some raises for raise levels and call| spots.
            i = int(rng.integers(len(acts))) if rng.random() < 0.3 else (acts.index("c") if "c" in acts else acts.index("k") if "k" in acts else 0)
            s = G.apply(s, acts[i])
    return sorted(out)


def _run(node, keys, table):
    r = subprocess.run([node, "--input-type=module", "-e", _NODE % json.dumps(TPGTO)], input=json.dumps({"keys": keys, "table": table}),
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout)


@pytest.mark.slow   # ~5 s: seeded c1 keys at three depths (b1 fields postflop)
def test_coarse_key_and_coarse_tables_match_python(node):
    keys = []
    for depth, tier in (("full", "mid"), ("pro", "pro"), ("basic", "beginner")):
        ks = _seeded_keys(depth, tier, 3, 3, 1)
        assert all(k.startswith({"pro": "p|", "basic": "b|"}.get(depth, "")) for k in ks if not k.startswith("call|")), depth
        assert any("|o" in k for k in ks), f"{depth}: no postflop key with b1 items reached"
        keys += ks
    for n in (2, 4, 5, 6):   # #645: L3 maps each player count's position names to their groups
        ks = _seeded_keys("full", "mid", n, 1, 2)
        assert {k.split("|")[0] for k in ks if not k.startswith("call|")} >= {"BB"}, n
        keys += ks
    policy, _ = H.load_policy(MID3)
    rng = np.random.default_rng(623)
    sample = [k for i, k in enumerate(policy) if i in set(rng.choice(len(policy), 1500, replace=False).tolist())]
    sample += [k for k in policy if k.startswith("call|")][:50]
    assert any(k.startswith("call|") for k in sample)
    keys += sample
    # A small table: mid-3 rows that share coarse keys, with two lengths under some of them.
    small = {k: policy[k] for k in sample[:400]}
    js = _run(node, keys, small)
    for k, cs in zip(keys, js["coarse"]):
        assert cs == [H.coarse_key(k, lv) for lv in range(1, len(H.LEVELS) + 1)], f"{k}: JS {cs}"
    groups = {(k.split("|")[1], cs[2].split("|")[0]) for k, cs in zip(keys, js["coarse"]) if k[0] not in "bcp"}
    assert {g for _, g in groups} == {"early", "late", "blind"} and {n for n, _ in groups} == {"n2", "n3", "n4", "n5", "n6"}
    py = H.coarse_tables(small)
    assert len(js["tables"]) == len(py) == 3
    for lv, (jt, pt) in enumerate(zip(js["tables"], py), 1):
        assert set(jt) == set(pt), f"L{lv}: coarse key sets differ"
        for ck, by_m in pt.items():
            assert set(jt[ck]) == {str(m) for m in by_m}, f"L{lv} {ck}: row lengths differ"
            for m, row in by_m.items():
                assert np.allclose(jt[ck][str(m)], row, atol=5e-7), f"L{lv} {ck} m={m}: JS {jt[ck][str(m)]} vs {row}"
    counts = {}
    for k in small:
        counts[H.coarse_key(k, 2)] = counts.get(H.coarse_key(k, 2), 0) + 1
    assert max(counts.values()) > 1, "the small table never averages two rows; pick keys that share a coarse key"


# Reads {"queries": [[key, m, top], ...], "table": {key: row}}; prints tpgto.js backoffRow for each query.
_NODE_ROW = """
import * as T from %s;
let src = ""; process.stdin.on("data", (c) => (src += c)); process.stdin.on("end", () => {
  const { queries, table, l1_rows, q } = JSON.parse(src);
  const pol = new Map(Object.entries(table).map(([k, r]) => [k, Float64Array.from(r)]));
  if (l1_rows) T.setL1Rows(pol, l1_rows, q);
  process.stdout.write(JSON.stringify(queries.map(([k, m, top]) => {
    const { row, from } = T.backoffRow(pol, k, m, "c1", top);
    return { row: row ? Array.from(row) : null, from };
  })));
});
"""
_NAMES = ("exact", *H.LEVELS, "L4", False)


def _js_rows(node, queries, table, l1_rows=None, q=1):
    r = subprocess.run([node, "--input-type=module", "-e", _NODE_ROW % json.dumps(TPGTO)],
                       input=json.dumps({"queries": queries, "table": table, "l1_rows": l1_rows, "q": q}),
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout)


def _l1_extra(l1_rows: dict, q: int) -> dict:
    """A policy file's `l1_rows` ({L1 key with `e*`: {step: row or [rows]}}, 0..q) as `measure`'s `l1_extra`."""
    out: dict = {}
    for g, by_step in l1_rows.items():
        for step, v in by_step.items():
            for row in (v if isinstance(v[0], list) else [v]):
                out.setdefault(_at(g.replace("|e*", "|e0"), int(step)), {})[len(row)] = [x / q for x in row]
    return out


def _assert_same(node, queries, table, l1_rows=None, q=1):
    """JS backoffRow == Python backoff_row(l4=top) on every query: same level, same row to 6 decimals. With
    `l1_rows`, Python adds them to L1 as `measure(l1_extra=...)` does (#804)."""
    tables = H.coarse_tables(table)
    for ck, by_m in _l1_extra(l1_rows or {}, q).items():   # web_hit_rate.measure: the table's rows win
        for m, row in by_m.items():
            tables[0].setdefault(ck, {}).setdefault(m, row)
    js = _js_rows(node, queries, table, l1_rows, q)
    seen = []
    for (k, m, top), j in zip(queries, js):
        row, level = H.backoff_row(table, tables, k, m, top)
        assert j["from"] == _NAMES[level], f"{k} m={m}: JS {j['from']} vs Python {_NAMES[level]}"
        if row is None:
            assert j["row"] is None, k
        else:
            assert np.allclose(j["row"], row, atol=5e-7), f"{k} m={m}: JS {j['row']} vs {row}"
            assert [round(x, 6) for x in j["row"]] == [round(float(x), 6) for x in row], k
        seen.append(_NAMES[level])
    return seen


def _at(k: str, v: int) -> str:
    parts = k.split("|")
    at = max(i for i, f in enumerate(parts) if H._EQ.fullmatch(f))
    return "|".join(parts[:at] + [f"e{v}"] + parts[at + 1:])


def test_l4_neighbor_cases_match_python(node):
    """#652 (a) both neighbors averaged, (b) one, (c) e0 / top boundary, (d) none -> uniform, (e) call| and b| keys."""
    mid, beg = K.TIER_K["mid"] - 1, K.TIER_K["beginner"] - 1
    base = "BB|n3|1|1|0|2|0|3|tc0|s4:4|u10|hn|go|ka|e5|o1v1k0"
    call = "call|1|2|3|fc|e4"
    basic = "b|blind|n3|1|1|0|2|0|tc0|ka|e2"
    table = {_at(base, 4): [1.0, 0.0, 0.0], _at(base, 6): [0.0, 0.5, 0.5],   # (a)
             _at(base, 1): [0.2, 0.3, 0.5],                                   # (b) e0 and e2 see only e1
             _at(base, mid - 1): [0.6, 0.4, 0.0], _at(base, mid + 1): [0.0, 0.0, 1.0],   # (c) above top: never
             _at(call, 3): [0.25, 0.75], _at(call, 5): [0.75, 0.25],          # (e) call|
             _at(basic, 3): [0.1, 0.9]}                                        # (e) b|, beginner top 4
    queries = [[base, 3, mid], [_at(base, 0), 3, mid], [_at(base, 2), 3, mid], [_at(base, mid), 3, mid],
               [base.replace("BB|", "BTN|", 1), 3, mid],   # (d) another position group: no row at e4/e6
               [base, 2, mid],                  # (d) neighbors only of another length
               [call, 2, mid], [_at(basic, beg), 2, beg], [_at(basic, 2), 2, beg], [_at(basic, 0), 2, beg]]
    seen = _assert_same(node, queries, table)
    assert seen == ["L4", "L4", "L4", "L4", False, False, "L4", "L4", "L4", False], seen
    js = _js_rows(node, queries[:4], table)
    assert js[0]["row"] == [0.5, 0.25, 0.25]          # (a) the mean of both
    assert js[1]["row"] == js[2]["row"] == [0.2, 0.3, 0.5]   # (b) one, and e0 reads only e1
    assert js[3]["row"] == [0.6, 0.4, 0.0]            # (c) top: e<top+1> is skipped


@pytest.mark.slow   # ~3 s: mid-3 keys against a table of a few of its rows
def test_backoff_row_with_l4_matches_python_on_mid3(node):
    policy, _ = H.load_policy(MID3)
    rng = np.random.default_rng(652)
    keys = list(policy)
    pick = rng.choice(len(keys), 2000, replace=False).tolist()
    table = {keys[i]: policy[keys[i]] for i in pick[:300]}
    queries = [[keys[i], len(policy[keys[i]]), K.TIER_K["mid"] - 1] for i in pick[300:]]
    queries += [[k, len(policy[k]), K.TIER_K["mid"] - 1] for k in keys if k.startswith("call|")][:50]
    seen = _assert_same(node, queries, table)
    assert {"L4", False} <= set(seen), f"levels reached: {sorted(map(str, set(seen)))}"


def test_l1_rows_backoff_matches_python(node):
    """#804: a file's `l1_rows` fill L1 only where the table builds no row of that (L1 key, length), on both sides;
    without the field the same queries give the old levels."""
    mid = K.TIER_K["mid"] - 1
    base = "BB|n3|1|1|0|2|0|3|tc0|s4:4|u10|hn|go|ka|e5|o1v1k0"
    group = H.coarse_key(base, 1).replace("|e5", "|e*")
    table = {_at(base, 3).replace("|o1v1k0", "|o2v2k2"): [0.1, 0.2, 0.7],   # L1 of e3 from the table: wins at m=3
             base.replace("|u10|", "|u5|"): [0.3, 0.3, 0.4],                # L2 of every u10 key
             "call|1|2|3|fc|e4": [0.5, 0.5]}
    l1_rows = {group: {"3": [[255, 0, 0], [0, 255]],   # m=3 loses to the table's row, m=2 is the file's
                       "5": [0, 255, 0],
                       "7": [[51, 102, 102]]}}           # a one-row [rows] value
    queries = [[base, 3, mid], [_at(base, 3), 3, mid], [_at(base, 3), 2, mid], [_at(base, 7), 3, mid],
               [_at(base, 6), 3, mid], [_at(base, 5), 2, mid], [base.replace("BB|", "BTN|", 1), 3, mid],
               [_at(base, 5).replace("|u10|", "|u5|"), 3, mid], ["call|1|2|3|fc|e4", 2, mid]]
    seen = _assert_same(node, queries, table, l1_rows, 255)
    assert seen == ["L1", "L1", "L1", "L1", "L4", False, False, "exact", "exact"], seen
    js = _js_rows(node, queries, table, l1_rows, 255)
    assert js[0]["row"] == [0.0, 1.0, 0.0] and js[1]["row"] == [0.1, 0.2, 0.7] and js[2]["row"] == [0.0, 1.0]
    assert np.allclose(js[3]["row"], [0.2, 0.4, 0.4])
    assert _assert_same(node, queries, table) == ["L2", "L1", False, False, "L4", False, False, "exact", "exact"]
