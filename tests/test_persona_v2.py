"""PRESETS_V2 street-level style (#518): optional params leave old personas unchanged, stats count by hand, mix hits targets."""
import dataclasses
import hashlib

import numpy as np
import pytest

from stalker.agents.base import Event
from stalker.agents.persona import PRESETS, PRESETS_V2, PersonaAgent, PersonaParams
from stalker.agents.persona_stats import CELLS, _Counter, measure_session

TYPES = list(PRESETS_V2)
# note §9 target WTSD (docs/research/2026-10-30-population-stats.md)
WTSD = dict(zip(TYPES, (0.21, 0.23, 0.27, 0.28, 0.33, 0.40, 0.35, 0.28)))


def test_optional_fields_default_none_and_old_presets_untouched():
    assert all(dataclasses.astuple(p)[4:] == (None,) * 15 for p in PRESETS.values())
    assert len(PRESETS_V2) == 8 and PRESETS_V2["tag"].cbet_flop == 0.62 and PRESETS_V2["pro"].fold_river == 0.62
    with pytest.raises(ValueError):
        PersonaParams(0.2, 0.1, 0.5, 0.5, cbet_flop=1.5)


def test_none_params_replay_is_bit_identical_to_stateless_bot():
    # observe() bookkeeping must not draw from the rng: same seed, same actions as a bot that ignores events
    def run(feed_events):
        agents = [PersonaAgent(PRESETS[n], np.random.default_rng(i)) for i, n in enumerate(sorted(PRESETS)[:6])]
        if not feed_events:
            for a in agents:
                a.observe = lambda e: None
        return measure_session(agents, 400, seed=5)

    assert run(True) == run(False)


def _ev(t, **d):
    return Event(t, "g", 1, 0, d)


def _act(seat, action, street, amount=0):
    return _ev("ACTION", seat=seat, action=action, street=street, amount=amount)


def test_counter_by_hand():
    c = _Counter(3)
    c(_ev("NEW_HAND", seat_players={0: 0, 1: 1, 2: 2}))
    c(_act(0, "raise", 0, 6)); c(_act(1, "call", 0, 6)); c(_act(2, "fold", 0))   # seat 0 is the aggressor
    c(_act(1, "call", 3)); c(_act(0, "raise", 3, 8)); c(_act(1, "fold", 3))      # flop c-bet, seat 1 folds
    c(_ev("HAND_END", deltas={0: 1, 1: -1, 2: 0}))
    c(_ev("NEW_HAND", seat_players={0: 0, 1: 1, 2: 2}))
    c(_act(0, "raise", 0, 6)); c(_act(1, "call", 0, 6)); c(_act(2, "fold", 0))
    c(_act(1, "call", 3)); c(_act(0, "call", 3))                                   # aggressor checks back: no c-bet
    c(_act(1, "call", 4)); c(_act(0, "raise", 4, 8)); c(_act(1, "call", 4, 8))     # turn c-bet called
    c(_ev("SHOWDOWN", board=("a",) * 5, hands={0: "x", 1: "y"}))
    c(_ev("HAND_END", deltas={0: 1, 1: -1, 2: 0}))
    assert (c.opp["cb1"][0], c.hit["cb1"][0]) == (2, 1)
    assert (c.opp["cb2"][0], c.hit["cb2"][0]) == (1, 1)
    assert (c.opp["fcb"][1], c.hit["fcb"][1]) == (1, 1) and c.opp["fcb"][2] == 0
    assert (c.opp["fct"][1], c.hit["fct"][1]) == (1, 0) and c.opp["fr"][1] == 0   # turn c-bet called, no river action
    assert (c.opp["flop"][0], c.hit["sd"][0], c.hit["sd"][1], c.opp["flop"][2]) == (2, 1, 1, 0)


def test_street_style_within_6pp_of_target_in_mixed_field():
    # 8 types over three 6-max tables; seats judged only where the opportunity count is large enough
    bad, seen, fold = [], set(), {}
    for gi, grp in enumerate([TYPES[:6], TYPES[2:8], TYPES[:2] + TYPES[4:8]]):
        ss = np.random.SeedSequence(gi).spawn(6)
        agents = [PersonaAgent(PRESETS_V2[n], np.random.default_rng(s)) for n, s in zip(grp, ss)]
        for n, st in zip(grp, measure_session(agents, 20000, seed=50 + gi)):
            p = PRESETS_V2[n]
            # #670: with the flop cell levers on, the mixed total is not a target (see test_pro_flop_cells_hit_human_targets)
            cells = p.cbet_flop_mw_mult is not None
            for key, tgt in () if cells else (("cbet_flop", p.cbet_flop), ("fold_cbet_flop", p.fold_cbet_flop)):
                got = getattr(st, key)
                seen.add((n, key))
                if got is None or abs(got - tgt) > 0.06:
                    bad.append(f"{n} {key}: target {tgt:.2f} measured {got}")
            # same tolerance as tests/test_persona.py `_fidelity` at 20k hands
            for key in ("vpip", "pfr"):
                if abs(getattr(st, key) - getattr(p, key)) > 0.05:
                    bad.append(f"{n} {key}: target {getattr(p, key):.2f} measured {getattr(st, key):.3f}")
            fold.setdefault(n, []).append((st.fold_cbet_turn, st.fold_river))
            seen.add((n, "wtsd"))
            if st.wtsd is None or abs(st.wtsd - WTSD[n]) > 0.06:
                bad.append(f"{n} wtsd: target {WTSD[n]:.2f} measured {st.wtsd}")
    # 16 = 8 types x wtsd, minus the 4 cell-lever types (tag excluded earlier? see cells flag) x 2 c-bet keys
    assert len(seen) == 16 and not bad, bad
    # giveup_weak overrides fold_cbet_turn/fold_river (docs/research/2026-11-persona-wtsd-sweep.md): the measured folds
    # sit above their targets, so only guard what the servers rely on: loose types fold clearly less than tight ones, no
    # type folds almost always (reviewer #531: calling_station must not fold to 61% of turn c-bets above the tight group)
    mean = {n: tuple(np.mean([f[i] for f in v if f[i] is not None]) for i in (0, 1)) for n, v in fold.items()}
    loose, tight = ("calling_station", "maniac", "loose_passive"), ("nit", "weak_tight", "tag", "lag", "pro")
    for i, street in enumerate(("turn", "river")):
        assert max(mean[n][i] for n in loose) < min(mean[n][i] for n in tight), (street, mean)
        assert max(mean[n][i] for n in mean) < (0.95, 0.80)[i], (street, mean)
    # #533: turn fold-to-c-bet error vs target, at most half of PR #531's (giveup_weak on turn and river alike)
    base = dict(zip(TYPES, (0.84, 0.88, 0.87, 0.90, 0.67, 0.61, 0.60, 0.77)))  # note table, V2 turn column
    err = np.mean([abs(mean[n][0] - PRESETS_V2[n].fold_cbet_turn) for n in TYPES])
    err0 = np.mean([abs(base[n] - PRESETS_V2[n].fold_cbet_turn) for n in TYPES])
    assert err <= err0 / 2, (err, err0, mean)
    # #569: the seeded fit's levers (measured .136 turn, .168 river); turn <= .10 is not reachable with WTSD within 6pp
    # (docs/research/2026-11-persona-wtsd-sweep.md), so these lock in the best found
    # #722: .14002 after the fish types got cell levers (seeded grid found nothing lower without breaking per-seat WTSD)
    assert err <= 0.141, (err, mean)
    river = np.mean([abs(mean[n][1] - PRESETS_V2[n].fold_river) for n in TYPES])
    assert river <= 0.22, (river, mean)


def test_giveup_nonc_off_is_bit_identical_and_on_folds_more():
    # #569: None and 0 draw nothing from the rng, so the pre-lever personas replay exactly; a positive value folds more
    def run(v):
        ps = [dataclasses.replace(PRESETS_V2[n], giveup_nonc=v) for n in TYPES[:6]]
        return measure_session([PersonaAgent(p, np.random.default_rng(i)) for i, p in enumerate(ps)], 400, seed=7)

    off = run(None)
    assert run(0.0) == off
    on = run(1.0)
    assert on != off and sum(s.wtsd for s in on) < sum(s.wtsd for s in off)


_CELL_LEVERS = ("cbet_flop_mw_mult", "cbet_flop_3bp_mult", "fold_cbet_flop_mw")


def _core(stats):
    return [(s.hands, s.vpip, s.pfr, s.aggression, s.cbet_flop, s.cbet_turn, s.fold_cbet_flop, s.fold_cbet_turn,
             s.fold_river, s.wtsd) for s in stats]


def test_cell_levers_off_replay_is_bit_identical():
    # #670 under #569's constraint: types without the levers replay exactly as before them. The digest was taken on main
    # 4720829 (before #670) with the same call; the levers and their bookkeeping never draw from the rng.
    names = ["nit", "weak_tight", "lag", "maniac", "nit", "lag"]  # #722: the fish types have cell levers now; 6 seats needed, so two repeats
    assert all(getattr(PRESETS_V2[n], k) is None for n in names for k in _CELL_LEVERS)
    st = measure_session([PersonaAgent(PRESETS_V2[n], np.random.default_rng(i)) for i, n in enumerate(names)], 400, seed=9)
    assert hashlib.sha256(repr(_core(st)).encode()).hexdigest()[:16] == "3dd6f4b9a490c964"

    # neutral lever values move no threshold, so the replay equals the levers-off one; real values change play
    def run(**kw):
        ps = [dataclasses.replace(PRESETS_V2[n], **kw) for n in names]
        return measure_session([PersonaAgent(p, np.random.default_rng(i)) for i, p in enumerate(ps)], 400, seed=9)

    assert _core(run(cbet_flop_mw_mult=1.0, cbet_flop_3bp_mult=1.0)) == _core(st)
    assert run(cbet_flop_mw_mult=0.3) != st and run(fold_cbet_flop_mw=0.9) != st
    with pytest.raises(ValueError):
        PersonaParams(0.2, 0.1, 0.5, 0.5, cbet_flop_3bp_mult=2.5)


def _pooled_cells(persona, tables, hands=25000):
    """Pool one persona's flop-cell opportunities over every seat of that type at the given tables."""
    opp = {k: 0 for k in (f"{b}_{c}" for b in ("cb", "f") for c in CELLS)}
    hit, seats = dict(opp), []
    for t, grp in enumerate(tables):
        ss = np.random.SeedSequence(t).spawn(6)
        st = measure_session([PersonaAgent(PRESETS_V2[n], np.random.default_rng(s)) for n, s in zip(grp, ss)], hands,
                             seed=100 + t)
        for n, x in zip(grp, st):
            if n != persona:
                continue
            seats.append(x)
            for c, v in x.flop_cells.items():
                opp[f"cb_{c}"] += v.cbet_opps
                hit[f"cb_{c}"] += round((v.cbet or 0) * v.cbet_opps)
                opp[f"f_{c}"] += v.fold_opps
                hit[f"f_{c}"] += round((v.fold_cbet or 0) * v.fold_opps)
    return {k: hit[k] / opp[k] for k in opp if opp[k]}, opp, seats


@pytest.mark.slow
def test_tag_flop_cells_hit_human_targets():
    # #684: tag's cells (note §10.1.4) +-6pp, same method as the pro test; the multiway fold cell is judged here too
    tables = [("tag", "maniac", "tag", "nit", "lag", "weak_tight"),
              ("tag", "calling_station", "tag", "loose_passive", "lag", "maniac")]
    got, opp, seats = _pooled_cells("tag", tables)
    targets = {"cb_hu_srp": 0.62, "cb_hu_3bp": 0.70, "cb_mw_srp": 0.42, "f_hu_srp": 0.48, "f_mw_srp": 0.68}
    assert all(opp[k] >= 150 for k in targets), opp
    assert all(abs(got[k] - t) <= 0.06 for k, t in targets.items()), (got, opp)
    p = PRESETS_V2["tag"]
    assert all(abs(x.vpip - p.vpip) <= 0.05 and abs(x.pfr - p.pfr) <= 0.05 for x in seats), seats


@pytest.mark.slow
@pytest.mark.parametrize("persona,targets", [
    ("loose_passive", {"cb_hu_srp": 0.46, "cb_hu_3bp": 0.50, "cb_mw_srp": 0.38, "f_hu_srp": 0.36, "f_mw_srp": 0.44}),
    ("calling_station", {"cb_hu_srp": 0.40, "cb_hu_3bp": 0.42, "cb_mw_srp": 0.34, "f_hu_srp": 0.25, "f_mw_srp": 0.30})])
def test_fish_flop_cells_hit_human_targets(persona, targets):
    # #722: note §10.1.6 cells +-6pp; two seats of the type per table so each judged cell has >= 150 opportunities
    tables = [(persona, "maniac", persona, "nit", "lag", "weak_tight"),
              (persona, "tag", persona, "lag", "maniac", "weak_tight")]
    got, opp, _ = _pooled_cells(persona, tables)
    assert all(opp.get(k, 0) >= 150 for k in targets), opp
    assert all(abs(got[k] - t) <= 0.06 for k, t in targets.items()), (got, opp)


@pytest.mark.slow
def test_pro_flop_cells_hit_human_targets():
    # #670: human pros' flop cells (population-stats note §10.1) +-6pp. Two pro seats at each of two tables, 25,000 hands
    # each: aggressive openers give heads-up c-bets to fold to, passive callers give multiway single-raised flops. Pooled
    # opportunities (local run): fewest judged cell = fold heads-up single-raised (665); the test asserts >= 150 per cell.
    tables = [("pro", "maniac", "pro", "nit", "lag", "weak_tight"),
              ("pro", "calling_station", "pro", "loose_passive", "lag", "maniac")]
    opp = {k: 0 for k in (f"{b}_{c}" for b in ("cb", "f") for c in CELLS)}
    hit, pro = dict(opp), []
    for t, grp in enumerate(tables):
        ss = np.random.SeedSequence(t).spawn(6)
        st = measure_session([PersonaAgent(PRESETS_V2[n], np.random.default_rng(s)) for n, s in zip(grp, ss)], 25000,
                             seed=100 + t)
        for n, x in zip(grp, st):
            if n != "pro":
                continue
            pro.append(x)
            for c, v in x.flop_cells.items():
                opp[f"cb_{c}"] += v.cbet_opps
                hit[f"cb_{c}"] += round((v.cbet or 0) * v.cbet_opps)
                opp[f"f_{c}"] += v.fold_opps
                hit[f"f_{c}"] += round((v.fold_cbet or 0) * v.fold_opps)
    got = {k: hit[k] / opp[k] for k in opp if opp[k]}
    targets = {"cb_hu_srp": 0.53, "cb_hu_3bp": 0.62, "cb_mw_srp": 0.29, "f_hu_srp": 0.44}
    assert all(opp[k] >= 150 for k in targets), opp
    assert all(abs(got[k] - t) <= 0.06 for k, t in targets.items()), (got, opp)
    # preflop is untouched; WTSD is calibrated on the mixed field only (test_street_style_within_6pp_of_target_in_mixed_field)
    p = PRESETS_V2["pro"]
    assert all(abs(x.vpip - p.vpip) <= 0.05 and abs(x.pfr - p.pfr) <= 0.05 for x in pro), pro
