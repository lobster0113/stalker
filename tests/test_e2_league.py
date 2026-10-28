import pytest

from stalker.e2.league import League


def test_league_records_generations_and_promotes_only_on_a_lower_exploit_gain():
    lg = League("beginner", seed=3)
    hist = lg.run(generations=3, iters_per_gen=30, exploiter_iters=40, hands=40)
    assert [g.gen for g in hist] == [1, 2, 3] and lg.history[0].field_bb is not None
    assert [g.iters for g in hist] == [30, 60, 90]
    best = None
    for g in hist:
        assert g.promoted == ((best is None or g.gain_bb + g.stderr_bb < best.gain_bb) and (g.vs_pool_bb is None or g.vs_pool_bb >= 0)
                              and g.vs_worst_persona_bb >= 0)
        if g.promoted:
            best = g
    assert len(lg.pool) == sum(g.promoted for g in hist) and hist[0].vs_pool_bb is None


def test_league_is_reproducible():
    a = League("beginner", seed=4).run(2, 20, 20, 20)
    b = League("beginner", seed=4).run(2, 20, 20, 20)
    assert a == b


def test_head_to_head_is_antisymmetric_and_a_policy_ties_itself():
    from referee.e2.exploiter import head_to_head
    from stalker.e2.abstraction import TIERS
    from stalker.e2.mccfr import MCCFR

    m = MCCFR(5, TIERS["beginner"])
    m.iterate(30)
    p = m.policy()
    a, _ = head_to_head(p, TIERS["beginner"], {}, TIERS["beginner"], 60, seed=2)
    b, _ = head_to_head({}, TIERS["beginner"], p, TIERS["beginner"], 60, seed=2)
    assert abs(a + b) < 1e-9          # same deals, seats swapped: zero-sum
    same, se = head_to_head(p, TIERS["beginner"], p, TIERS["beginner"], 60, seed=2)
    assert abs(same) <= 3 * se + 1e-9


def test_persona_field_is_reported_and_can_block_promotion():
    lg = League("beginner", seed=3, personas=("calling_station", "tag"))
    g = lg.run(1, 30, 40, 40)[0]
    assert g.worst_persona in ("calling_station", "tag") and g.field_stderr_bb > 0
    assert g.promoted == (g.vs_worst_persona_bb >= 0)
    off = League("beginner", seed=3, personas=()).run(1, 30, 40, 40)[0]
    assert off.field_bb is None and off.promoted and (off.gain_bb, off.stderr_bb) == (g.gain_bb, g.stderr_bb)


def test_field_reports_the_gate_q1_lower_bound_from_independent_deals():
    lg = League("beginner", seed=5, personas=("calling_station", "tag"))
    g = lg.run(1, 20, 20, 40)[0]
    assert g.field_ci95_low_bb == pytest.approx(g.field_bb - 1.96 * g.field_stderr_bb, abs=2e-4)


def test_exploiter_defaults_to_the_policy_tier_and_a_share_of_its_iterations(monkeypatch):
    # #247: the first CI league's BASELINE exploiter lost to every champion; it now learns at the policy's
    # tier and trains at least `exploiter_ratio` x the policy's total iterations.
    import stalker.e2.league as L
    from stalker.e2.abstraction import TIERS

    calls = []
    real = L.exploit

    def spy(fixed, fixed_abs, iters, hands, seed, ex_abs, strategy):
        calls.append({"iters": iters, "ex_abs": ex_abs, "strategy": strategy})
        return real(fixed, fixed_abs, iters=2, hands=hands, seed=seed, ex_abs=ex_abs, strategy=strategy)

    monkeypatch.setattr(L, "exploit", spy)
    hist = League("mid", seed=1, personas=()).run(2, 40, 10, 10)
    assert [c["iters"] for c in calls] == [20, 40]            # max(10, 0.5 x 40), max(10, 0.5 x 80)
    assert all(c["ex_abs"] == TIERS["mid"] and c["strategy"] == "current" for c in calls)
    assert [g.exploiter_iters for g in hist] == [20, 40]
    calls.clear()
    League("mid", seed=1, personas=(), exploiter_tier="beginner", exploiter_ratio=0.0,
           exploiter_strategy="average").run(1, 40, 10, 10)
    assert calls == [{"iters": 10, "ex_abs": TIERS["beginner"], "strategy": "average"}]
