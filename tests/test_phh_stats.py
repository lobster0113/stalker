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


# Multiway single-raised: open, two callers; c-bet, e folds, Pluribus raises, opener folds
HAND_MW_SRP = rec(["p3 f", "p4 cbr 210", "p5 cc", "p6 cc", "p1 f", "p2 f", "d db 7d5h9d",
                   "p4 cbr 300", "p5 f", "p6 cbr 900", "p4 f"],
                  [9950, 9900, 10000, 9490, 9790, 10870])
# Multiway 3-bet pot: the 3-bettor checks the flop (opportunity, no c-bet); checked down
HAND_MW_3BP = rec(["p3 cbr 200", "p4 cbr 600", "p5 f", "p6 cc", "p1 f", "p2 f", "p3 cc",
                   "d db 2c3c4d", "p3 cc", "p4 cc", "p6 cc", "d db 9h", "p3 cc", "p4 cc", "p6 cc",
                   "d db Kh", "p3 cc", "p4 cc", "p6 cc"],
                  [9950, 9900, 9400, 11250, 10000, 9400])


def _cell(counts, p, cell):
    c = counts[p]
    return tuple(c[f"{k}_{cell}"] for k in ("cb_opp", "cb", "fcb_opp", "fcb"))


def test_cbet_cells_one_hand_each():
    a = ps.hand_counts(HAND_A)  # heads-up single-raised, SB folds to the c-bet
    assert _cell(a, "d", "hu_srp") == (1, 1, 0, 0) and _cell(a, "a", "hu_srp") == (0, 0, 1, 1)
    b = ps.hand_counts(HAND_B)  # heads-up 3-bet pot, opener calls the c-bet
    assert _cell(b, "Pluribus", "hu_3bp") == (1, 1, 0, 0) and _cell(b, "e", "hu_3bp") == (0, 0, 1, 0)
    m = ps.hand_counts(HAND_MW_SRP)
    assert _cell(m, "d", "mw_srp") == (1, 1, 0, 0)
    assert _cell(m, "e", "mw_srp") == (0, 0, 1, 1) and _cell(m, "Pluribus", "mw_srp") == (0, 0, 1, 0)
    t = ps.hand_counts(HAND_MW_3BP)
    assert _cell(t, "d", "mw_3bp") == (1, 0, 0, 0)
    assert all(_cell(t, p, "mw_3bp")[2] == 0 for p in t)  # no c-bet, nobody faced one
    for counts in (a, b, m, t):  # each hand lands in exactly one cell
        hit = {cl for p in counts for cl in ps.CELLS if any(_cell(counts, p, cl))}
        assert len(hit) == 1


def _cells_sum_to_totals(tot):
    for c in tot.values():
        assert sum(c[f"cb_opp_{cl}"] for cl in ps.CELLS) == c["cb_opp"]
        assert sum(c[f"cb_{cl}"] for cl in ps.CELLS) == c["cb"]


def test_cells_sum_to_flop_cbet_totals():
    _cells_sum_to_totals(ps.aggregate([HAND_A, HAND_B, HAND_C, HAND_MW_SRP, HAND_MW_3BP]))
    from referee.gate_r.phh import load_sample
    _cells_sum_to_totals(ps.aggregate(load_sample()))


def test_cell_rates_and_interval():
    cr = ps.cell_rates(ps.aggregate([HAND_A, HAND_B, HAND_MW_SRP])["human"])
    assert cr["hu_srp"]["cbet"] == 100.0 and cr["hu_srp"]["fold_to_cbet"] == 100.0
    assert cr["mw_srp"]["fold_opps"] == 1 and cr["mw_3bp"]["cbet"] is None
    lo, hi = cr["hu_srp"]["cbet_ci95"]
    assert 0 < lo < 100 and hi == 100.0
