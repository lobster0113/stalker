from pathlib import Path

import numpy as np
import pytest

from referee.e3 import preflop_probe as P
from stalker.core.cards import hand_class

K5 = 5
SERVED_MID = Path(__file__).resolve().parents[1] / "web" / "app" / "policy" / "mid-6.json"


def _parts(key):
    p = key.split("|")
    return p, int(p[1]), int(p[-1][1:])


def _pick(acts, want):
    for a in want:
        if a in acts:
            return [1.0 if x == a else 0.0 for x in acts]
    return None


def _policy(limp_top: bool):
    """Unopened, the top equity step opens (or, with `limp_top`, limps) and the rest fold. Everyone folds
    to a raise or an all-in, and nobody bets postflop. With `limp_top` the big blind raises any limp, so
    a limp loses the bet while an open takes the blinds: a 2.5bb leak with almost no noise. Without
    it, opening is already the best first action (a limp checks down for less than the blinds)."""
    def pol(key, acts):
        p, street, step = _parts(key)
        free = "f" not in acts
        if free:
            bb_option = street == 0 and p[0] != "call" and p[3] == "0"
            return _pick(acts, ["r"] if (limp_top and bb_option) else ["k", "c"])
        if street > 0 or p[0] == "call" or p[3] != "0" or step < K5 - 1:
            return _pick(acts, ["f"])
        return _pick(acts, ["c"] if limp_top else ["r"])
    return pol


def _table(pol):
    return {"policy": pol, "k": K5, "depth": "full", "players": 3, "menu": "v1", "raise_cap": 3}


def test_group_combos():
    assert len(P.group_combos("AA")) == 6 and len(P.group_combos("AKs")) == 4 and len(P.group_combos("AKo")) == 12
    assert all(hand_class(*c) == "AQs" for c in P.group_combos("AQs"))
    with pytest.raises(ValueError):
        P.group_combos("AX")


def test_probe_flags_a_policy_that_limps_aces():
    r = P.probe(_table(_policy(limp_top=True)), 40, seed=1, spots=("first_in",), seats=[0], groups=("AA",))
    c = r["cells"][0]
    assert c["deals"] == 40 and c["actions"]["c"]["row"] == 1.0
    assert c["leak"] and c["best"] in ("r", "a")
    assert c["open_minus_limp"]["r"]["ci"][0] > 2.0


def test_probe_does_not_flag_a_policy_that_raises_aces():
    r = P.probe(_table(_policy(limp_top=False)), 40, seed=1, spots=("first_in",), seats=[0, 1],
                groups=("AA", "AKo"))
    assert r["leaks"] == 0
    first = r["cells"][0]
    assert first["actions"]["r"]["row"] == 1.0 and first["actions"]["r"]["vs_row_bb"] == 0.0


def test_vs_open_reaches_only_single_raised_pots():
    seen = []

    def spy(key, acts):
        seen.append(key)
        return _policy(False)(key, acts)
    res, tries = P.deals(_table(spy), "vs_open", 2, "AA", 5, np.random.SeedSequence(3))
    assert len(res) == 5 and tries >= 5
    assert all(acts == ("f", "c", "r", "a") for acts, _, _ in res)
    # Gate L: the policy only ever sees TP keys (public items + the hero's own equity step).
    assert seen and all(k.split("|")[-1].startswith("e") for k in seen)


def test_probe_is_reproducible_and_worker_independent():
    # Two chunks (CHUNK deals each) so that workers=2 really splits the cell; chunk seeds depend only on
    # the cell and the chunk index. A loaded policy file, because worker processes must pickle the table.
    t = P.load(SERVED_MID)
    kw = dict(seed=2, spots=("first_in",), seats=[1], groups=("KK",))
    a = P.probe(t, 2 * P.CHUNK, **kw)
    assert a == P.probe(t, 2 * P.CHUNK, **kw)
    assert a == P.probe(t, 2 * P.CHUNK, workers=2, **kw)



@pytest.mark.slow
def test_probe_flags_the_served_mid_policy_limping_aces():
    # #413 criterion 1 / #391: the served mid policy (average strategy) limps AA first in from HJ/CO most
    # of the time. Pre-registered cells: first_in, HJ and CO, AA, 300 deals, seed 1. If the served file
    # changes and the leak is gone, this fails on purpose: re-register the cells or close #391.
    assert SERVED_MID.exists(), f"{SERVED_MID} missing: the served policy moved; update this test"
    r = P.probe(P.load(SERVED_MID), 300, seed=1, spots=("first_in",), seats=[1, 2], groups=("AA",))
    assert r["leaks"] >= 1, P.table(r)
    assert any(c["open_minus_limp"]["r"]["ci"][0] > 0 for c in r["cells"] if c["leak"]), P.table(r)


def test_flag_needs_both_the_threshold_and_the_corrected_bound():
    def cell(g, se):
        return {"best": "r", "actions": {"r": {"vs_row_bb": g, "vs_row_se": se}, "c": {"vs_row_bb": 0.0, "vs_row_se": 0.0}}}
    cells = [cell(2.0, 0.5), cell(2.0, 1.5), cell(0.4, 0.01)]
    z = P.flag(cells)
    assert z > P.Z95                      # six tests: stricter than a single 95% bound
    assert [c["leak"] for c in cells] == [True, False, False]


# --- c1 web policy files (#823) ---
import hashlib
import json

from stalker.e3 import tp_key as K
from stalker.tools import policy_leaks as PL

MID5 = Path(__file__).resolve().parents[1] / "web" / "app" / "policy" / "mid-5.json"
LEGACY_GOLDEN = "0e3425d4a40a6ba8c20c3758005e74080ca6947f3c6e714739dfeecf2f8c0fc6"   # pre-#823 main code, rows hit (6-max, spy-keyed)


def _c1_policy():
    """A tiny c1 table: a few real keys of the served 5-max file."""
    d = json.loads(MID5.read_text(encoding="utf-8"))
    q = d["q"]
    keys = [k for k in d["policy"] if k.split("|")[0] not in ("b", "p", "call")][:50]
    return {k: [x / q for x in d["policy"][k]] for k in keys}, d


def _legacy6_file(tmp_path):
    """A legacy (no key_variant) 6-max file whose rows the probe really hits: keys recorded from a spy run,
    rows a fixed function of the key (crc32), so the file never changes with the served policies."""
    import zlib
    seen = {}

    def spy(key, acts):
        seen[key] = tuple(acts)
        return None
    P.probe({"policy": spy, "k": 5, "depth": "full", "players": 6, "menu": "v1", "raise_cap": 3},
            6, 4, spots=("first_in",), seats=[0, 3], groups=("AA", "AKs"))
    q = 255
    policy = {}
    for key, acts in sorted(seen.items()):
        h = zlib.crc32(key.encode()) % 7
        row = [1] * len(acts)
        row[h % len(acts)] += 3
        tot = sum(row)
        v = [round(x * q / tot) for x in row]
        v[0] += q - sum(v)
        policy[key] = v
    f = tmp_path / "legacy6.json"
    f.write_text(json.dumps({"schema": "stalker.web.policy", "q": q, "k": 5, "depth": "full", "players": 6,
                             "menu": "v1", "policy": policy}, sort_keys=True), encoding="utf-8")
    return f, len(policy)


def test_legacy_file_result_is_unchanged(tmp_path):
    # No key_variant: the old dict path with rows that are actually returned (the rows hit), fixed seed.
    f, n = _legacy6_file(tmp_path)
    assert n > 5
    t = P.load(f)
    assert "variant" not in t and isinstance(t["policy"], dict)
    r = P.probe(t, 6, 4, spots=("first_in",), seats=[0, 3], groups=("AA", "AKs"))
    assert "key_variant" not in r and "backoff_levels" not in r
    got = hashlib.sha256((json.dumps(r, indent=1) + "\n").encode()).hexdigest()
    assert got == LEGACY_GOLDEN, got


def test_c1_lookup_exact_l1_rows_and_uniform():
    rows, _ = _c1_policy()
    key = next(iter(rows))
    m = len(rows[key])
    pol = P.WebPolicy(rows)
    assert pol.lookup(key, m) == (rows[key], "L0")                       # 1. exact key
    parts = key.split("|")
    at = max(i for i, f in enumerate(parts) if f.startswith("e") and f[1:].isdigit())
    miss = "|".join(parts[:at] + ["e98"] + parts[at + 1:])
    assert pol.lookup(miss, m) == (None, "uniform")                       # 3. nothing to fall back on
    extra_row = [1.0] + [0.0] * (m - 1)
    ck = P.W.coarse_key(miss, 1)
    pol = P.WebPolicy(rows, {ck: {m: extra_row}})
    assert pol.lookup(miss, m) == (extra_row, "L1")                       # 2. l1_rows supply L1
    spr = key.split("|")
    spr[P.W._SPR_AT] = "98"                                               # only the SPR step differs: L2 drops it
    assert pol.lookup("|".join(spr), m)[1] == "L2"


def test_c1_file_load_keeps_variant_and_l1_rows(tmp_path):
    rows, d = _c1_policy()
    d = {**d, "policy": {k: [round(x * d["q"]) for x in v] for k, v in rows.items()}, "l1_rows": None}
    key = next(iter(rows))
    parts = P.W.coarse_key(key, 1).split("|")   # the exporter's groups are L1 keys with the equity step wildcarded
    at = max(i for i, f in enumerate(parts) if f.startswith("e") and f[1:].isdigit())
    group = "|".join(parts[:at] + ["e*"] + parts[at + 1:])
    parts = key.split("|")
    at = max(i for i, f in enumerate(parts) if f.startswith("e") and f[1:].isdigit())
    d["l1_rows"] = {group: {"97": [255] + [0] * (len(rows[key]) - 1)}}
    f = tmp_path / "c1.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    t = P.load(f)
    assert t["variant"] == "c1" and t["l1_extra"]
    miss = "|".join(parts[:at] + ["e97"] + parts[at + 1:])
    row, level = t["policy"].lookup(miss, len(rows[key]))
    assert level == "L1" and row == [1.0] + [0.0] * (len(rows[key]) - 1)   # probabilities, not 0..q integers


def test_c1_hero_key_reads_only_public_line_and_own_cards():
    # Gate L: the backoff key is public key + the hero's own equity step; other seats' hole cards do not enter.
    t = P.load(MID5)
    rng = np.random.default_rng(5)
    mine = P.group_combos("AA")[0]
    s = P._deal(rng, t, 0, mine)
    rest = [c for c in range(52) if c not in mine]
    others = [rest[i:i + 2] for i in range(0, 8, 2)]
    hole2 = list(s.hole)
    for q, h in zip((1, 2, 3, 4), reversed(others)):
        hole2[q] = tuple(h)
    s2 = s._replace(hole=tuple(hole2))
    assert s.hole != s2.hole
    with K.using_variant("c1"):
        ranges = K.initial_ranges(s.n)
        assert P._hero_level(t, s, 0, ranges) == P._hero_level(t, s2, 0, ranges)
        assert K.public_key(s, 0, t["depth"]) == K.public_key(s2, 0, t["depth"])


@pytest.mark.slow
def test_c1_probe_smoke_mid5(tmp_path):
    out = tmp_path / "o.json"
    assert P.main([str(MID5), "--deals", "20", "--seats", "0", "--groups", "AA", "--json", str(out)]) == 0
    r = json.loads(out.read_text(encoding="utf-8"))
    assert r["key_variant"] == "c1"
    assert sum(r["backoff_levels"].values()) == r["cells"][0]["deals"] == 20


def test_policy_leaks_rejects_non_6max_with_fix():
    with pytest.raises(ValueError, match=r"6-player policy file"):
        PL.build({"probe": PL.PROBE, "players": 5, "cells": []}, "mid", "mid-5.json")
