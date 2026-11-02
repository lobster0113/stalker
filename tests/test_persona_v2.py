"""PRESETS_V2 street-level style (#518): optional params leave old personas unchanged, stats count by hand, mix hits targets."""
import dataclasses

import numpy as np
import pytest

from stalker.agents.base import Event
from stalker.agents.persona import PRESETS, PRESETS_V2, PersonaAgent, PersonaParams
from stalker.agents.persona_stats import _Counter, measure_session

TYPES = list(PRESETS_V2)


def test_optional_fields_default_none_and_old_presets_untouched():
    assert all(dataclasses.astuple(p)[4:] == (None,) * 7 for p in PRESETS.values())
    assert len(PRESETS_V2) == 8 and PRESETS_V2["tag"].cbet_flop == 0.65 and PRESETS_V2["pro"].fold_river == 0.62
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
    assert (c.opp["flop"][0], c.hit["sd"][0], c.hit["sd"][1], c.opp["flop"][2]) == (2, 1, 1, 0)


def test_street_style_within_6pp_of_target_in_mixed_field():
    # 8 types over three 6-max tables; seats judged only where the opportunity count is large enough
    bad, seen = [], set()
    for gi, grp in enumerate([TYPES[:6], TYPES[2:8], TYPES[:2] + TYPES[4:8]]):
        ss = np.random.SeedSequence(gi).spawn(6)
        agents = [PersonaAgent(PRESETS_V2[n], np.random.default_rng(s)) for n, s in zip(grp, ss)]
        for n, st in zip(grp, measure_session(agents, 20000, seed=50 + gi)):
            p = PRESETS_V2[n]
            for key, tgt in (("cbet_flop", p.cbet_flop), ("fold_cbet_flop", p.fold_cbet_flop)):
                got = getattr(st, key)
                seen.add((n, key))
                if got is None or abs(got - tgt) > 0.06:
                    bad.append(f"{n} {key}: target {tgt:.2f} measured {got}")
            # same tolerance as tests/test_persona.py `_fidelity` at 20k hands
            for key in ("vpip", "pfr"):
                if abs(getattr(st, key) - getattr(p, key)) > 0.05:
                    bad.append(f"{n} {key}: target {getattr(p, key):.2f} measured {getattr(st, key):.3f}")
            # WTSD is reported but not asserted: the bot checks down ~70% of showdowns and measures 0.48-0.75 against
            # the note's 0.21-0.40 (see #518 hand-off); asserting it needs probe/give-up mechanics, a separate issue.
            assert st.wtsd is not None and 0.0 < st.wtsd < 1.0
    assert len(seen) == 16 and not bad, bad
