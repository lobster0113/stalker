import numpy as np
import pytest

from referee.e2 import lbr as L
from stalker.core.cards import cards
from stalker.e2 import game as G
from stalker.e2.abstraction import bucket, ehs_table
from stalker.e2.mccfr import MCCFR, infoset


def test_mccfr_is_deterministic_and_policies_are_distributions():
    a, b = MCCFR(5), MCCFR(5)
    a.iterate(60)
    b.iterate(60)
    pa, pb = a.policy(), b.policy()
    assert pa == pb and len(pa) > 50
    assert all(abs(sum(v) - 1) < 1e-9 and min(v) >= 0 for v in pa.values())


def test_buckets_order_hands_by_strength_on_a_board():
    board = tuple(cards("Kc7d2s"))
    set_k = bucket(tuple(cards("KsKd")), board)
    air = bucket(tuple(cards("4h3h")), board)
    assert set_k == 9 and air <= 3
    assert np.isnan(ehs_table(board)).sum() == 1326 - 1176  # combos using a board card


def test_equity_vs_range_matches_a_known_matchup():
    rng = np.random.default_rng(0)
    w = np.zeros(1326)
    kk = [i for i, c in enumerate(L.COMBOS) if set(c) == set(cards("KsKd"))][0]
    w[kk] = 1
    eq = np.mean([L.equity_vs_range(tuple(cards("AhAd")), (), w, rng) for _ in range(30)])
    assert eq == pytest.approx(0.82, abs=0.06)  # AA vs KK preflop ≈ 82%


def test_lbr_crushes_a_policy_that_always_folds_to_a_bet():
    def folder(key, acts):
        return [1.0 if a == "f" else 0.0 for a in acts] if "f" in acts else None
    r = L.lbr(folder, player=0, hands=40, seed=1)
    assert r.mean_bb > 0.9  # it raises every hand and collects at least the big blind


def test_lbr_is_reproducible():
    assert L.lbr({}, 1, 10, seed=4) == L.lbr({}, 1, 10, seed=4)


def _head_to_head(pol, hands, seed):
    """pol vs the uniform policy, both seats, same deals: pol's winnings per hand (bb)."""
    def probs(s, mine):
        acts = G.legal(s)
        p = pol.get(infoset(s)) if mine else None
        return np.asarray(p) if p is not None and len(p) == len(acts) else np.full(len(acts), 1 / len(acts))
    wins = []
    for seat in (0, 1):
        rng = np.random.default_rng(seed)
        for _ in range(hands):
            s = G.deal(rng)
            while not s.done:
                q = probs(s, s.to_act == seat)
                s = G.apply(s, G.legal(s)[int(rng.choice(len(q), p=q / q.sum()))])
            v = G.payoff(s) / G.BB
            wins.append(v if seat == 0 else -v)
    return np.array(wins)


@pytest.mark.slow
def test_training_beats_the_untrained_policy_beyond_noise():
    # Significance test (#178 review): 3000 iterations, then 6000 hands per seat against the uniform
    # (0-iteration) policy on the same deals; the edge must exceed 2 standard errors. An LBR-based
    # significance test at this size is too noisy (local: z = 0.98 with 300 hands per seat), so LBR is
    # only smoke-checked below; LBR curves over iterations are in the research notes and CI records.
    m = MCCFR(1)
    m.iterate(3000)
    w = _head_to_head(m.policy(), 6000, seed=5)
    se = w.std(ddof=1) / np.sqrt(len(w))
    assert w.mean() > 2 * se, (w.mean(), se)
    trained = L.exploitability_lb(m.policy(), 200, seed=11)["lbr_bb"]
    uniform = L.exploitability_lb({}, 200, seed=11)["lbr_bb"]
    assert trained < uniform  # smoke check only (same deals for both)


def test_checkpoint_resumes_exactly(tmp_path):
    a = MCCFR(9)
    a.iterate(25)
    a.save(tmp_path / "ck.json")
    b = MCCFR.load(tmp_path / "ck.json")
    a.iterate(15)
    b.iterate(15)
    c = MCCFR(9)
    c.iterate(40)
    assert a.policy() == b.policy() == c.policy() and b.iterations == 40


def test_progress_log_rows(tmp_path):
    import json

    from stalker.e2.mccfr import main
    log = tmp_path / "run.jsonl"
    assert main(["--iters", "30", "--seed", "4", "--log", str(log), "--every", "10"]) == 0
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert [r["iteration"] for r in rows] == [10, 20, 30]
    assert all(set(r) == {"iteration", "seed", "infosets", "seconds"} and r["seed"] == 4 for r in rows)
