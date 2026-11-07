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

# Reads {"keys": [...], "table": {key: row}} on stdin; prints both coarse levels of every key and the coarse tables.
_NODE = """
import * as T from %s;
let src = ""; process.stdin.on("data", (c) => (src += c)); process.stdin.on("end", () => {
  const { keys, table } = JSON.parse(src);
  const tabs = T.coarseTables(new Map(Object.entries(table).map(([k, r]) => [k, Float64Array.from(r)])));
  const out = tabs.map((t) => Object.fromEntries([...t].map(([ck, byM]) => [ck, Object.fromEntries([...byM].map(([m, r]) => [m, Array.from(r)]))])));
  process.stdout.write(JSON.stringify({ coarse: keys.map((k) => [T.coarseKey(k, 1), T.coarseKey(k, 2)]), tables: out }));
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
    policy, _ = H.load_policy(MID3)
    rng = np.random.default_rng(623)
    sample = [k for i, k in enumerate(policy) if i in set(rng.choice(len(policy), 1500, replace=False).tolist())]
    sample += [k for k in policy if k.startswith("call|")][:50]
    assert any(k.startswith("call|") for k in sample)
    keys += sample
    # A small table: mid-3 rows that share coarse keys, with two lengths under some of them.
    small = {k: policy[k] for k in sample[:400]}
    js = _run(node, keys, small)
    for k, (c1, c2) in zip(keys, js["coarse"]):
        assert (c1, c2) == (H.coarse_key(k, 1), H.coarse_key(k, 2)), f"{k}: JS {c1} / {c2}"
    py = H.coarse_tables(small)
    assert len(js["tables"]) == len(py) == 2
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
