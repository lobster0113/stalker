"""Range-policy fixed point arms (#411): key churn, exploitability and reproducibility on small games."""
import json

import numpy as np
import pytest

from referee.anchors.toy import leduc as L
from referee.anchors.toy.game import infosets
from stalker import train_jobs as T
from stalker.vcfr import fixed_point as F
from stalker.vcfr import solver as S
from stalker.vcfr.leduc import LeducGame

SEEDS = (1, 2, 3, 4)
ARMS = ("A", "B10", "C10", "D")
ITERS = 120


@pytest.fixture(scope="module")
def runs():
    # Test-sized experiment: the tiny river menu and Leduc, four paired seeds (about 25 s).
    return [F.run_seed(s, ("river-tiny", "leduc"), ITERS, ARMS) for s in SEEDS]


def test_leduc_public_game_matches_the_referee_game():
    g = LeducGame()
    m = S.VectorCFR(g)
    m.iterate(200)
    strat = m.materialize()
    assert abs(S.ev(g, strat, 0) - L.GAME_VALUE_APPROX) < 0.003
    assert S.exploitability(g, strat) < 0.01
    assert 3 * len(g.decision_nodes()) == len(infosets(L.game()))      # a node per public history, a row per rank


def test_fixed_ranges_never_churn(runs):
    for r in runs:
        for name, g in r["games"].items():
            d = g["arms"]["D"]
            assert d["refreshes"] > 0, name                 # compared at every checkpoint, not assumed
            assert d["churn_early"] == d["churn_late"] == 0.0, name


def test_average_range_churn_is_high_early_and_falls(runs):
    for name in ("river-tiny", "leduc"):
        b = [r["games"][name]["arms"]["B10"] for r in runs]
        early, late = np.mean([x["churn_early"] for x in b]), np.mean([x["churn_late"] for x in b])
        assert early > 0.05, name
        # Not per seed: on some boards many combos sit on a quantile edge with near-equal equity, and
        # blocker shifts keep flipping them. Leduc has three ranks per node, so one rank is a third.
        assert late < (0.75 if name == "river-tiny" else 1.0) * early, (name, early, late)


def test_current_and_average_ranges_settle_on_the_river(runs):
    # #414 corrected #393: neither diverges on the river; both reach about the TP cost of fixed keys.
    for r in runs:
        g = r["games"]["river-tiny"]
        for arm in ("A", "B10"):
            assert g["arms"][arm]["expl_final"] < 0.6, (r["seed"], arm)
        assert g["combo"]["expl_final"] < 0.1


def test_leduc_range_sensitive_keys_cost_more_than_fixed_ones(runs):
    # Equity thirds move Leduc's ranks between keys; with policy-dependent ranges no arm settles near D.
    for r in runs:
        a = r["games"]["leduc"]["arms"]
        assert a["D"]["expl_final"] < min(a[x]["expl_final"] for x in ("A", "B10", "C10")), r["seed"]
        # D's keys read under its own ranges (the TP info contract) are a different, much worse policy.
        assert a["D"]["expl_policy_keys"] > 3 * a["D"]["expl_final"]


def test_snapshot_keys_are_frozen_within_an_epoch():
    g, keyer = F.make_game("river-tiny", 1)
    m = S.VectorCFR(g, keyer, "snapshot", refresh=10)
    seen = []
    for _ in range(25):
        m.iterate(1)
        seen.append((m.refreshes, F.training_keys(m)))
    for (ra, ka), (rb, kb) in zip(seen, seen[1:]):
        if ra == rb:
            assert np.array_equal(ka, kb)
    assert seen[-1][0] == 3


def test_runs_are_reproducible():
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k != "ms_per_iter"}
        return x
    a = F.run_seed(3, ("leduc",), 30, ("A", "C10"))
    b = F.run_seed(3, ("leduc",), 30, ("A", "C10"))
    assert strip(a) == strip(b)
    assert F.run_seed(4, ("leduc",), 30, ("A",))["games"]["leduc"]["arms"]["A"]["expl_final"] != \
        a["games"]["leduc"]["arms"]["A"]["expl_final"]                     # seeds pick different games


def test_aggregate_pairs_seeds_and_renders(runs):
    agg = F.aggregate(json.loads(json.dumps(runs)))          # as summarize reads them back from JSON
    a = agg["games"]["river-tiny"]["arms"]["B10"]
    assert a["expl_final"]["n"] == len(SEEDS) and a["expl_final"]["ci95"] is not None
    assert "expl_final_minus_A" in a and "expl_final_minus_A" not in agg["games"]["river-tiny"]["arms"]["A"]
    text = F.table(agg)
    assert text.count("\n") == 1 + 2 * (1 + len(ARMS)) and "own ranges" in text


def test_train_job_is_registered(tmp_path):
    assert "vcfr-fixed-point" in T.JOBS and "vcfr-fixed-point" not in T.RESUMABLE
    with pytest.raises(ValueError):
        F.make_game("river-huge", 1)
