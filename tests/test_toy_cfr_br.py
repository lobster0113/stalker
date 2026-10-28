import pytest

from referee.anchors.toy import (
    best_response_value,
    expected_value,
    exploitability,
    infosets,
    kuhn,
    leduc,
)
from stalker.toy import bottleneck as b
from stalker.toy import cfr_br as c


def _value_of_choice(root, strategy, br_player, choice):
    full = dict(strategy)
    for i, (p, acts) in infosets(root).items():
        if p == br_player:
            full[i] = [1.0 if a == choice[i] else 0.0 for a in range(len(acts))]
    ev = expected_value(root, full)
    return ev if br_player == 0 else -ev


@pytest.mark.parametrize("game", [kuhn.game, leduc.game])
@pytest.mark.parametrize("br_player", [0, 1])
def test_best_response_choice_reaches_the_referee_value(game, br_player):
    g = game()
    s = b.solve(g, b.kuhn_key(2) if game is kuhn.game else b.leduc_key(2, 1), 20)
    choice = c.best_response(g, s, br_player)
    assert _value_of_choice(g, s, br_player, choice) == pytest.approx(best_response_value(g, s, br_player), abs=1e-12)


def test_kuhn_full_summary_cfr_br_approaches_equilibrium():
    g = kuhn.game()
    assert exploitability(g, c.solve(g, b.kuhn_key(3), 1000)) < 5e-3
    assert exploitability(g, c.asymmetric(g, b.kuhn_key(3), 500)) < 1e-3


def test_kuhn_one_bucket_both_methods_hit_the_constant_policy_floor():
    g = kuhn.game()
    for s in (c.solve(g, b.kuhn_key(1), 300), c.asymmetric(g, b.kuhn_key(1), 300)):
        for hist in ("", "k", "b", "kb"):
            rows = [s[f"{card}:{hist}"] for card in kuhn.CARDS]
            assert rows[0] == rows[1] == rows[2]
        assert exploitability(g, s) == pytest.approx(1 / 3, abs=1e-3)


def test_kuhn_direct_optimization_beats_translation_on_a_coarse_summary():
    # Two buckets merge J and Q: the abstract game's equilibrium is far from the least exploitable
    # two-bucket strategy (translation 0.17 vs about 0.06 locally).
    g = kuhn.game()
    tr = exploitability(g, b.solve(g, b.kuhn_key(2), 500))
    assert exploitability(g, c.asymmetric(g, b.kuhn_key(2), 500)) < tr - 0.05
    assert exploitability(g, c.solve(g, b.kuhn_key(2), 500)) < tr - 0.05


def test_cfr_br_strategy_uses_only_its_players_infosets_and_merges_by_key():
    g = leduc.game()
    key = b.leduc_key(1, 2)
    s = c.CFRBR(g, key, 1)
    s.iterate(3)
    st = s.strategy()
    own = {i for i, (p, _) in infosets(g).items() if p == 1}
    assert set(st) == own
    for i in own:
        for j in own:
            if key(i) == key(j):
                assert st[i] == st[j]


def test_recall_and_nesting_checks():
    g = leduc.game()
    assert c.perfect_recall(g, b.leduc_key(3, 3))
    assert c.perfect_recall(g, b.leduc_key(1, 2))           # round 1 forgets nothing it knew
    assert not c.perfect_recall(g, b.leduc_key(2, 1))       # round 2 forgets the round-1 bucket
    assert c.refines(g, b.leduc_key(3, 3), b.leduc_key(2, 2))
    assert c.refines(g, b.leduc_key(2, 2), b.leduc_key(1, 1))
    assert not c.refines(g, b.leduc_key(1, 1), b.leduc_key(2, 2))
    assert all(c.perfect_recall(kuhn.game(), b.kuhn_key(k)) for k in (1, 2, 3))


def test_monotonicity_warnings_classify_by_method_and_recall():
    rows = [{"buckets": [1], "perfect_recall": True, "translation": 0.1, "asymmetric": 0.1, "cfr_br": 0.1},
            {"buckets": [2], "perfect_recall": True, "translation": 0.3, "asymmetric": 0.05, "cfr_br": 0.2},
            {"buckets": [3], "perfect_recall": True, "translation": 0.0, "asymmetric": 0.0, "cfr_br": 0.0}]
    w = {(x["method"], tuple(x["fine"]), tuple(x["coarse"])): x["kind"] for x in c.monotonicity_warnings("kuhn", rows)}
    assert w == {("translation", (2,), (1,)): "pathology", ("cfr_br", (2,), (1,)): "defect"}


@pytest.mark.slow
def test_leduc_translation_vs_direct_table():
    rows = {tuple(r["buckets"]): r for r in c.compare("leduc", 200)}
    assert set(rows) == set(b.LEDUC_LEVELS)
    for r in rows.values():
        assert r["cfr_br"] > 0 and r["asymmetric"] > 0 and r["translation"] > 0
    # Coarsest summary: optimizing against the full-game opponent loses far less than translating.
    assert rows[(1, 1)]["asymmetric"] < rows[(1, 1)]["translation"] - 0.5
    assert rows[(1, 1)]["cfr_br"] < rows[(1, 1)]["translation"] - 0.5
    # Full summary: the asymmetric game is the full game, so it matches unconstrained CFR+ closely.
    assert rows[(3, 3)]["asymmetric"] < 0.02
