import pytest

from referee.anchors.toy import exploitability, infosets, kuhn, leduc
from stalker.toy import bottleneck as b
from stalker.toy.cfr import CFRPlus


def _unconstrained(root, iters):
    s = CFRPlus(root)
    s.iterate(iters)
    return exploitability(root, s.average_strategy())


def test_full_information_bottleneck_equals_unconstrained_kuhn():
    g = kuhn.game()
    assert exploitability(g, b.solve(g, b.kuhn_key(3), 500)) == pytest.approx(_unconstrained(g, 500), abs=1e-12)


def test_one_bucket_kuhn_policy_ignores_the_card():
    g = kuhn.game()
    s = b.solve(g, b.kuhn_key(1), 1000)
    for hist in ("", "k", "b", "kb"):
        rows = [s[f"{c}:{hist}"] for c in kuhn.CARDS]
        assert rows[0] == rows[1] == rows[2]
    assert exploitability(g, s) > 0.3


def test_kuhn_cost_falls_as_the_summary_resolves_more():
    g = kuhn.game()
    e = [exploitability(g, b.solve(g, b.kuhn_key(k), 1000)) for k in (1, 2, 3)]
    assert e[0] > e[1] > e[2] and e[2] < 1e-3


def test_lifted_strategy_covers_every_infoset():
    g = leduc.game()
    s = b.lift(g, {k: [1 / len(a)] * len(a) for k, (_, a) in infosets(b.abstract(g, b.leduc_key(2, 2))).items()},
               b.leduc_key(2, 2))
    assert set(s) == set(infosets(g))


def test_leduc_keys_keep_board_and_history():
    key = b.leduc_key(1, 1)
    assert key("KJ:bc/b") == "Jb0:bc/b"
    assert key("Q:kb") == "b0:kb"
    # Full resolution maps distinct private cards to distinct buckets on every board.
    full = b.leduc_key(3, 3)
    for d in leduc.RANKS:
        assert len({full(c + d + ":kk/") for c in leduc.RANKS}) == 3


def test_leduc_strength_orders_pairs_first():
    assert b.leduc_strength("J", "J") == 1.0
    assert b.leduc_strength("K", None) > b.leduc_strength("Q", None) > b.leduc_strength("J", None)


@pytest.mark.slow
def test_leduc_bottleneck_curve():
    rows = {tuple(r["buckets"]) if r["buckets"] else None: r["exploitability"] for r in b.curve("leduc", 300)}
    assert rows[(3, 3)] == pytest.approx(rows[None], abs=1e-12)    # full summary = unconstrained
    assert rows[(1, 1)] > rows[(2, 2)] > rows[(2, 3)] > rows[(3, 3)]
    # Resolving the river (round 2) matters more than resolving round 1.
    assert rows[(1, 3)] < rows[(3, 1)]
