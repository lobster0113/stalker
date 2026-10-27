from stalker.e2.league import League


def test_league_records_generations_and_promotes_only_on_a_lower_exploit_gain():
    lg = League("beginner", seed=3)
    hist = lg.run(generations=3, iters_per_gen=30, exploiter_iters=40, hands=40)
    assert [g.gen for g in hist] == [1, 2, 3] and hist[0].promoted and lg.champion
    assert [g.iters for g in hist] == [30, 60, 90]
    best = hist[0]
    for g in hist[1:]:
        assert g.promoted == (g.gain_bb + g.stderr_bb < best.gain_bb)
        if g.promoted:
            best = g


def test_league_is_reproducible():
    a = League("beginner", seed=4).run(2, 20, 20, 20)
    b = League("beginner", seed=4).run(2, 20, 20, 20)
    assert a == b
