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
