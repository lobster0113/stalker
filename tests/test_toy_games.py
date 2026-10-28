import json

import pytest

from referee.anchors.toy import best_response_value, exploitability, expected_value, infosets, kuhn, leduc
from referee.anchors.toy.game import CHANCE, PLAYER, TERMINAL, Node, finalize
from stalker.toy.cfr import CFRPlus
from stalker.toy.train import run


def _check_fold(root):
    """Check when possible, fold when facing a bet."""
    return {k: [1.0 if a in ("k", "f") else 0.0 for a in acts] for k, (_, acts) in infosets(root).items()}


@pytest.mark.parametrize("alpha", [0.0, 1 / 6, 1 / 3])
def test_kuhn_equilibrium_family_has_value_minus_one_eighteenth(alpha):
    g = kuhn.game()
    s = kuhn.nash(alpha)
    assert expected_value(g, s) == pytest.approx(kuhn.GAME_VALUE, abs=1e-12)
    assert exploitability(g, s) == pytest.approx(0.0, abs=1e-12)
    # Best response to an equilibrium earns exactly the game value, no more.
    assert best_response_value(g, s, 0) == pytest.approx(kuhn.GAME_VALUE, abs=1e-12)
    assert best_response_value(g, s, 1) == pytest.approx(-kuhn.GAME_VALUE, abs=1e-12)


def test_kuhn_check_fold_exploitability_matches_hand_calculation():
    # Against check-fold, always betting wins the ante (1) every hand, for either seat.
    g = kuhn.game()
    s = _check_fold(g)
    assert best_response_value(g, s, 0) == pytest.approx(1.0)
    assert best_response_value(g, s, 1) == pytest.approx(1.0)
    assert exploitability(g, s) == pytest.approx(1.0)


def test_uniform_exploitability_matches_published_values():
    # NashConv of the uniform policy: Kuhn 11/12, Leduc 4.747222 (OpenSpiel reference values).
    assert exploitability(kuhn.game(), {}) == pytest.approx(11 / 24, abs=1e-12)
    assert 2 * exploitability(leduc.game(), {}) == pytest.approx(4.747222, abs=1e-6)


def test_leduc_tree_shape():
    g = leduc.game()
    info = infosets(g)
    assert len(info) == 288
    assert sum(g.probs) == pytest.approx(1.0)
    assert info["K:"] == (0, ("k", "b"))
    assert info["Q:br"] == (0, ("c", "f"))          # two raises used up
    assert info["JK:kk/b"] == (1, ("c", "f", "r"))


def test_leduc_showdown_and_fold_payoffs():
    g = leduc.game()

    def walk(n, path):
        for step in path:
            if n.kind == CHANCE:
                n = n.children[step]
            else:
                n = n.children[n.actions.index(step)]
        return n

    # Deals are ordered (player 0 rank, player 1 rank): (K, J) is child 2*3+0; public J is child 0.
    kj = g.children[6]
    assert kj.infoset == "K:"
    end = walk(kj, ["b", "c", 0, "b", "c"])
    assert end.kind == TERMINAL and end.utility == -(1 + 2 + 4)   # J pairs the board: player 1 wins 7
    fold = walk(kj, ["b", "r", "f"])
    assert fold.kind == TERMINAL and fold.utility == -3            # player 0 bet 2 more then folded


def test_finalize_rejects_inconsistent_infosets():
    leaf = Node(TERMINAL)
    bad = Node(CHANCE, probs=(0.5, 0.5), children=[
        Node(PLAYER, player=0, infoset="x", actions=("a",), children=[leaf]),
        Node(PLAYER, player=1, infoset="x", actions=("a",), children=[Node(TERMINAL)]),
    ])
    with pytest.raises(ValueError, match="keys must encode"):
        finalize(bad)


def test_strategy_must_be_a_distribution():
    with pytest.raises(ValueError, match="summing to 1"):
        exploitability(kuhn.game(), {"K:": [0.5, 0.6]})


def test_cfr_plus_solves_kuhn():
    solver = CFRPlus(kuhn.game())
    solver.iterate(1000)
    s = solver.average_strategy()
    assert exploitability(solver.root, s) < 1e-3
    assert expected_value(solver.root, s) == pytest.approx(kuhn.GAME_VALUE, abs=1e-3)


def test_cfr_plus_is_deterministic():
    a, b = CFRPlus(kuhn.game()), CFRPlus(kuhn.game())
    a.iterate(50)
    b.iterate(50)
    assert a.average_strategy() == b.average_strategy()


def test_train_cli_writes_log_and_strategy(tmp_path):
    out = tmp_path / "kuhn.jsonl"
    rows = run("kuhn", 200, 100, out)
    lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert [r["iteration"] for r in lines] == [100, 200] == [r["iteration"] for r in rows]
    assert lines[1]["exploitability"] < lines[0]["exploitability"]
    saved = json.loads(out.with_suffix(".strategy.json").read_text(encoding="utf-8"))
    assert saved["seed"] == 0 and set(saved["strategy"]) == set(infosets(kuhn.game()))


def test_train_cli_records_seed_and_cfr_plus_ignores_it(tmp_path):
    from stalker.toy.train import main

    assert main(["--game", "kuhn", "--iters", "10", "--seed", "1", "--out", str(tmp_path / "a.jsonl")]) == 0
    assert main(["--game", "kuhn", "--iters", "10", "--seed", "7", "--out", str(tmp_path / "b.jsonl")]) == 0
    a = [json.loads(x) for x in (tmp_path / "a.jsonl").read_text(encoding="utf-8").splitlines()]
    b = [json.loads(x) for x in (tmp_path / "b.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["seed"] for r in a} == {1} and {r["seed"] for r in b} == {7}
    assert [r["exploitability"] for r in a] == [r["exploitability"] for r in b]


@pytest.mark.slow
def test_cfr_plus_solves_leduc_and_matches_published_value():
    rows = run("leduc", 500, 100, None)
    expl = [r["exploitability"] for r in rows]
    assert all(b < a for a, b in zip(expl, expl[1:])), expl
    assert expl[-1] < 2e-3
    assert rows[-1]["game_value"] == pytest.approx(leduc.GAME_VALUE_APPROX, abs=2e-3)
