"""Flop c-bet cells in persona_stats (#641): same definition as phh_stats, cells sum to the totals."""
import numpy as np

from stalker.agents.base import Event
from stalker.agents.persona import PRESETS_V2, PersonaAgent
from stalker.agents.persona_stats import CELLS, _Counter, flop_cell, measure_session
from stalker.cash.presets import preset
from stalker.cash.session import run_cash_session
from stalker.tools import phh_stats as ps
from tests.test_phh_stats import HAND_A, HAND_B, HAND_C, HAND_MW_3BP, HAND_MW_SRP


def _ev(t, **d):
    return Event(t, "g", 1, 0, d)


def _act(seat, action, street, amount=0):
    return _ev("ACTION", seat=seat, action=action, street=street, amount=amount)


def _cell(c, s, cl):
    return (c.opp[f"cb1_{cl}"][s], c.hit[f"cb1_{cl}"][s], c.opp[f"fcb_{cl}"][s], c.hit[f"fcb_{cl}"][s])


def test_flop_cell():
    assert [flop_cell(2, 1), flop_cell(2, 2), flop_cell(3, 1), flop_cell(4, 3)] == list(CELLS)


def test_hand_made_events_land_in_expected_cells():
    c = _Counter(4)
    # heads-up single-raised: seat 0 opens, seat 1 calls, flop c-bet called
    c(_ev("NEW_HAND", seat_players={0: 0, 1: 1, 2: 2, 3: 3}))
    c(_act(0, "raise", 0, 6)); c(_act(1, "call", 0, 6)); c(_act(2, "fold", 0)); c(_act(3, "fold", 0))
    c(_act(1, "call", 3)); c(_act(0, "raise", 3, 8)); c(_act(1, "call", 3, 8))
    c(_ev("HAND_END", deltas={0: 0, 1: 0, 2: 0, 3: 0}))
    # multiway 3-bet pot: 0 opens, 1 three-bets, 2 and 0 call; 1 c-bets, 2 folds, 0 folds
    c(_ev("NEW_HAND", seat_players={0: 0, 1: 1, 2: 2, 3: 3}))
    c(_act(0, "raise", 0, 6)); c(_act(1, "raise", 0, 18)); c(_act(2, "call", 0, 18)); c(_act(3, "fold", 0))
    c(_act(0, "call", 0, 12))
    c(_act(0, "call", 3)); c(_act(1, "raise", 3, 20)); c(_act(2, "fold", 3)); c(_act(0, "fold", 3))
    c(_ev("HAND_END", deltas={0: 0, 1: 0, 2: 0, 3: 0}))
    assert _cell(c, 0, "hu_srp") == (1, 1, 0, 0) and _cell(c, 1, "hu_srp") == (0, 0, 1, 0)
    assert _cell(c, 1, "mw_3bp") == (1, 1, 0, 0)
    assert _cell(c, 2, "mw_3bp") == (0, 0, 1, 1) and _cell(c, 0, "mw_3bp") == (0, 0, 1, 1)
    assert all(_cell(c, s, cl) == (0, 0, 0, 0) for s in range(4) for cl in ("hu_3bp", "mw_srp"))


def _counter_session(hands, seed):
    names = list(PRESETS_V2)[:6]
    ss = np.random.SeedSequence(seed).spawn(6)
    agents = [PersonaAgent(PRESETS_V2[n], np.random.default_rng(s)) for n, s in zip(names, ss)]
    cfg = preset("cash_6max_100bb", hands=hands)
    c = _Counter(cfg.seats)
    run_cash_session(cfg, agents, np.random.default_rng(seed), observer=c)
    return c, agents


def test_cells_sum_to_totals_in_fixed_seed_session():
    c, _ = _counter_session(400, 11)
    for s in range(6):
        for b in ("cb1", "fcb"):
            assert sum(c.opp[f"{b}_{cl}"][s] for cl in CELLS) == c.opp[b][s]
            assert sum(c.hit[f"{b}_{cl}"][s] for cl in CELLS) == c.hit[b][s]
    assert sum(c.opp["cb1_mw_srp"]) > 0 and sum(c.opp["fcb_hu_srp"]) > 0  # not vacuous


def test_seat_stats_cells_and_old_fields():
    names = list(PRESETS_V2)[:6]
    st = measure_session([PersonaAgent(PRESETS_V2[n], np.random.default_rng(i)) for i, n in enumerate(names)],
                         300, seed=3)
    for x in st:
        assert set(x.flop_cells) == set(CELLS)
        opps = sum(v.cbet_opps for v in x.flop_cells.values())
        hits = sum(round(v.cbet * v.cbet_opps) for v in x.flop_cells.values() if v.cbet_opps)
        assert (x.cbet_flop is None) == (opps == 0)
        if opps:
            assert abs(x.cbet_flop - hits / opps) < 1e-12


def phh_events(rec):
    """PHH record -> the cash session's public events (seat i = PHH player i+1)."""
    n = len(rec["players"])
    out = [_ev("NEW_HAND", seat_players={i: i for i in range(n)})]
    committed = [0] * n
    committed[0], committed[1] = rec["blinds_or_straddles"][0], rec["blinds_or_straddles"][1]
    cur, board = committed[1], 0
    for a in rec["actions"]:
        t = a.split()
        if t[0] == "d":
            if t[1] == "db":
                board += len(t[2]) // 2
                committed, cur = [0] * n, 0
            continue
        i, kind = int(t[0][1:]) - 1, t[1]
        if kind == "sm":
            continue
        if kind == "f":
            out.append(_act(i, "fold", board))
        elif kind == "cc":
            out.append(_act(i, "call", board, cur - committed[i]))
            committed[i] = cur
        else:
            cur = committed[i] = int(t[2])
            out.append(_act(i, "raise", board, cur))
    out.append(_ev("HAND_END", deltas={i: 0 for i in range(n)}))
    return out


def test_same_cells_as_phh_stats():
    from referee.gate_r.phh import load_sample
    recs = [HAND_A, HAND_B, HAND_C, HAND_MW_SRP, HAND_MW_3BP] + [r for r in load_sample()[:400] if len(r["players"]) == 6]
    for rec in recs:
        c = _Counter(6)
        for e in phh_events(rec):
            c(e)
        want = ps.hand_counts(rec)
        for i, p in enumerate(rec["players"]):
            for cl in CELLS:
                w = want[p]
                assert _cell(c, i, cl) == (w[f"cb_opp_{cl}"], w[f"cb_{cl}"], w[f"fcb_opp_{cl}"], w[f"fcb_{cl}"]), (rec["actions"], p, cl)
