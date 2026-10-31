"""Browser TP-GTO port (#335): the vector generator runs, the committed vectors and asset are current,
and the node test (web/app/test/tpgto.test.mjs) matches them exactly when node is installed."""
import json
import subprocess

import numpy as np
import pytest

from stalker.e3 import tp_key as K
from stalker.e2.eq_view import EQ_RUNOUTS
from stalker.tools import web_vectors as W


@pytest.fixture(scope="module")
def committed() -> dict:
    return json.loads(W.VECTORS.read_text(encoding="utf-8"))


def test_generator_tiny_build_has_the_schema():
    v = W.build(hands=1, iters=1, players=(6,), tiers=("pro",), rng_count=2)
    assert v["schema"] == W.SCHEMA and v["schema_version"] == W.SCHEMA_VERSION
    h = v["hands"][0]
    assert h["n"] == 6 and h["tier"] == "pro" and sorted(h["perm"]) == list(range(52))
    d = h["decisions"][0]
    assert len(d["steps"]) == 1326 and d["key"].startswith(d["public"]) and len(d["sums"]) == 6
    assert len(v["rng"]) == 2 and all(len(r["runouts"]) == EQ_RUNOUTS for r in v["rng"])


def test_committed_vectors_cover_the_spec_and_are_current(committed):
    v = committed
    assert v["schema"] == W.SCHEMA and v["schema_version"] == W.SCHEMA_VERSION
    c = v["constants"]
    assert c["TIER_K"] == K.TIER_K and c["NUT_BASE"] == K.NUT_BASE and c["NUT_K"] == K.NUT_K, \
        "tp_key constants changed: run `python -m stalker.tools.web_vectors` and update web/app/tpgto.js"
    s = W.summary(v)
    assert s["decisions"] >= 200 and all(s["by_street"][st] > 0 for st in "0123")
    assert s["call_keys"] > 0 and s["board_nut"] > 0
    assert all(s["by_n"][n] > 0 for n in W.PLAYERS) and all(s["by_tier"][t] > 0 for t in W.TIERS)
    # One (players, tier) block rebuilt from scratch must equal the committed one (the generator is seeded
    # per block, so a subset reproduces it); a mismatch means the Python side changed.
    p = v["params"]
    sub = W.build(p["hands"], p["iters"], p["seed"], players=(6,), tiers=("pro",), rng_count=0)
    mine = [h for h in v["hands"] if h["n"] == 6 and h["tier"] == "pro"]
    stale = "web/app/test/vectors.json is stale: run `python -m stalker.tools.web_vectors`"
    # Discrete fields exactly; floats to 1e-12, because another numpy build may differ in the last ulp
    # (the node test still checks JS against the committed vectors exactly).
    exact = ("a", "legal", "public", "steps", "nut", "key")
    assert len(sub["hands"]) == len(mine), stale
    for got, want in zip(sub["hands"], mine):
        assert (got["n"], got["tier"], got["perm"], got["board"], got["payoff"]) == \
            (want["n"], want["tier"], want["perm"], want["board"], want["payoff"]), stale
        assert len(got["decisions"]) == len(want["decisions"]), stale
        for g, w in zip(got["decisions"], want["decisions"]):
            assert {f: g[f] for f in exact} == {f: w[f] for f in exact}, stale
            assert np.allclose(g["sums"], w["sums"], rtol=0, atol=1e-12), stale
    pg, pw = sub["policies"]["6/pro"], v["policies"]["6/pro"]
    assert pg.keys() == pw.keys(), stale
    assert all(len(pg[k]) == len(pw[k]) and np.allclose(pg[k], pw[k], rtol=0, atol=1e-12) for k in pg), stale
    assert W.rng_vectors(5, p["seed"]) == v["rng"][:5]


def test_committed_menu_vectors_are_current(committed):
    # The real/tp6 block (#386) is cheap to rebuild whole: no training, no equity.
    want = committed["menus"]
    got = W.menu_vectors(len(want) // (len(W.MENU_RULES) * len(W.MENU_PLAYERS)), committed["params"]["seed"])
    stale = "web/app/test/vectors.json menus are stale: run `python -m stalker.tools.web_vectors`"
    assert len(got) == len(want), stale
    for g, w in zip(got, want):
        assert {k: g[k] for k in g if k != "decisions"} == {k: w[k] for k in w if k != "decisions"}, stale
        for dg, dw in zip(g["decisions"], w["decisions"]):
            assert {k: dg[k] for k in dg if k != "split"} == {k: dw[k] for k in dw if k != "split"}, stale
            for (ag, pg), (aw, pw) in zip(dg.get("split", ()), dw.get("split", ())):
                assert ag == aw and abs(pg - pw) <= 1e-12, stale
    s = W.summary(committed)
    assert s["menu_bets_split"] >= 30, "too few between-size bets in the menu vectors"
    assert {(h["menu"], h["raise_cap"]) for h in want} == set(W.MENU_RULES)


def test_equity_asset_is_current():
    assert json.loads(W.ASSET.read_text(encoding="utf-8")) == W.equity_table(), \
        "web/app/assets/hu_equity.json is stale: run `python -m stalker.tools.web_vectors`"


def test_node_port_matches_vectors(node):
    r = subprocess.run([node, "--test", str(W.ROOT / "web" / "app" / "test" / "tpgto.test.mjs")],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]


def test_committed_hte_vectors_are_current(committed):
    # #417: the page's translationError is checked against these; rebuilding them is cheap (no equity).
    assert committed["hte"] == W.hte_vectors(committed["params"]["seed"]), \
        "web/app/test/vectors.json hte block is stale: run `python -m stalker.tools.web_vectors`"
    flags = [f for x in committed["hte"] for _, f in x["cases"]]
    assert any(flags) and not all(flags)
