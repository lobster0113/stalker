from stalker.tools import phh_stats as ps

NAMES = ["a", "b", "c", "d", "e", "Pluribus"]
BASE = {"players": NAMES, "blinds_or_straddles": [50, 100, 0, 0, 0, 0], "starting_stacks": [10000] * 6}


def rec(actions, fin):
    return {**BASE, "actions": actions, "finishing_stacks": fin}


# SB calls an open, flop c-bet folds out
HAND_A = rec(["p3 f", "p4 cbr 210", "p5 f", "p6 f", "p1 cc", "p2 f", "d db 7d5h9d", "p1 cc", "p4 cbr 300", "p1 f"],
             [9790, 9900, 10000, 10360, 10000, 10000])
# 3-bet pot to showdown; p6 (bot) wins
HAND_B = rec(["p3 f", "p4 f", "p5 cbr 200", "p6 cbr 700", "p1 f", "p2 f", "p5 cc",
              "d db 2c3c4d", "p5 cc", "p6 cbr 500", "p5 cc", "d db 9h", "p5 cc", "p6 cc",
              "d db Kh", "p5 cc", "p6 cc", "p5 sm 7s7d"],
             [10000, 9900, 10000, 10000, 8800, 11350])
HAND_B["finishing_stacks"][0] = 9950
# SB completes, BB checks his option (not voluntary)
HAND_C = rec(["p3 f", "p4 f", "p5 f", "p6 f", "p1 cc", "p2 cc", "d db 2c3c4d", "p1 cc", "p2 cc",
              "d db 9h", "p1 cc", "p2 cc", "d db Kh", "p1 cc", "p2 cc"], [10000] * 6)


def test_fixed_hands_counts():
    a = ps.hand_counts(HAND_A)
    assert (a["d"]["vpip"], a["d"]["pfr"], a["d"]["cb_opp"], a["d"]["cb"], a["d"]["bets"]) == (1, 1, 1, 1, 1)
    assert (a["a"]["vpip"], a["a"]["pfr"], a["a"]["flop"], a["a"]["calls"], a["a"]["wtsd"]) == (1, 0, 1, 0, 0)
    assert a["b"]["tb_opp"] == 1 and a["b"]["vpip"] == 0  # BB folds to the open: 3-bet chance, not VPIP
    assert a["c"]["tb_opp"] == 0  # folded before any raise
    b = ps.hand_counts(HAND_B)
    p6 = b["Pluribus"]
    assert (p6["tb_opp"], p6["tb"], p6["cb_opp"], p6["cb"], p6["wtsd"], p6["sd_won"]) == (1, 1, 1, 1, 1, 1)
    assert (b["e"]["calls"], b["e"]["tb_opp"], b["e"]["sd_won"], b["e"]["showdowns"]) == (1, 0, 0, 1)
    assert b["a"]["wtsd"] == 0
    c = ps.hand_counts(HAND_C)
    assert c["a"]["vpip"] == 1 and c["b"]["vpip"] == 0 and c["b"]["flop"] == 1 and c["b"]["wtsd"] == 1


def test_aggregate_rates_and_determinism():
    recs = [HAND_A, HAND_B, HAND_C]
    t = ps.aggregate(recs)
    assert t == ps.aggregate(recs)
    assert t["bot"]["hands"] == 3 and t["human"]["hands"] == 15
    r = ps.rates(t["bot"])
    assert r["VPIP"] == round(100 / 3, 1) and r["3bet"] == 50.0 and r["flop_cbet"] == 100.0
    assert r["W$SD"] == 100.0 and ps.rates(t["human"])["AF"] is not None


def test_short_tables_skipped():
    assert ps.hand_counts({**HAND_A, "players": ["a", "b"]}) == {}


def test_sample_runs():
    from referee.gate_r.phh import load_sample
    r = ps.rates(ps.aggregate(load_sample()[:200])["human"])
    assert 0 < r["VPIP"] < 100 and r["PFR"] <= r["VPIP"]
