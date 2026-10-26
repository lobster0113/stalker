import dataclasses
import importlib
import inspect
import pkgutil
import re
from pathlib import Path

import numpy as np
import pytest

import stalker
from referee import gate_l
from referee.gate_l import Report, check_l7, contract_pipeline, record_game
from stalker.core.cards import COMBOS, card
from stalker.env.contract import DECISION_CONTEXT_VERSION, DecisionContext, TeacherContext, decision_context
from stalker.env.teacher import opp_range_label
from stalker.observe.builder import ObservationBuilder
from stalker.tournament.config import load_preset

ROOT = Path(__file__).resolve().parent.parent


def _leaky_labels(obs, private, teacher, builder):
    """Card removal with the opponents' real cards: the classic hidden-card leak."""
    dc, labels = contract_pipeline(obs, private, teacher, builder)
    dead = {c for seat, cs in private.hole_cards.items() if seat != obs.seat for c in cs}
    return dc, labels + (tuple(sorted(dead)),)


def _leaky_policy_input(obs, private, teacher, builder):
    dc, labels = contract_pipeline(obs, private, teacher, builder)
    return dc + repr(private.deck[:1]), labels


def _leak_free_but_different_teacher(obs, private, teacher, builder):
    return contract_pipeline(obs, private, teacher, builder)


def test_l7_passes_for_the_contract_pipeline():
    r = Report()
    check_l7(r)
    assert r.ok and r.counts["L7"][0] == r.counts["L7"][1] >= 6


@pytest.mark.parametrize("fake", [_leaky_labels, _leaky_policy_input])
def test_l7_catches_hidden_card_use(fake):
    r = Report()
    check_l7(r, {"fake": fake})
    assert not r.ok and "differ only in hidden cards" in r.failures[0]


def test_hidden_worlds_keep_public_cards_and_vary_hidden_ones():
    cfg = load_preset("6max_sng_wta")
    obs = next(o for o, _ in record_game(cfg, 71, "l7").decisions if o.board)
    worlds = gate_l.hidden_worlds(obs, 20, np.random.default_rng(0))
    others = [s for s in obs.in_hand if s != obs.seat]
    assert all(w.hole_cards[obs.seat] == tuple(obs.hole_cards) for w in worlds)
    assert len({w.hole_cards[others[0]] for w in worlds}) > 1
    for w in worlds:
        shown = set(obs.hole_cards) | set(obs.board)
        assert not shown & {c for s in others for c in w.hole_cards[s]}


def _annotation_names(fn) -> set[str]:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return set()
    return {re.sub(r"[^A-Za-z_].*", "", str(p.annotation).split(".")[-1].strip("'\""))
            for p in sig.parameters.values()}


def test_no_function_takes_both_teacher_context_and_private_world_state():
    offenders, seen = [], 0
    for m in pkgutil.walk_packages(stalker.__path__, "stalker."):
        try:
            mod = importlib.import_module(m.name)
        except ImportError:
            continue  # optional extras (torch)
        for _, obj in inspect.getmembers(mod):
            fns = [obj] if inspect.isfunction(obj) else (
                [f for _, f in inspect.getmembers(obj, inspect.isfunction)] if inspect.isclass(obj) else [])
            for fn in fns:
                names = _annotation_names(fn)
                if "TeacherContext" in names:
                    seen += 1
                    if "PrivateWorldState" in names:
                        offenders.append(f"{fn.__module__}.{fn.__qualname__}")
    assert seen >= 1, "the scan found no TeacherContext consumer; it is not looking where it should"
    assert not offenders, f"take TeacherContext or PrivateWorldState, never both: {offenders}"


def test_signature_scan_would_catch_a_mixed_function():
    from stalker.env.contract import PrivateWorldState  # noqa: F401

    def bad(po, teacher: "TeacherContext", world: "PrivateWorldState"):
        return None
    assert {"TeacherContext", "PrivateWorldState"} <= _annotation_names(bad)


def _first_decision(preflop: bool):
    cfg = load_preset("6max_sng_wta")
    tap = record_game(cfg, 71, "dc")
    obs = next(o for o, _ in tap.decisions if bool(o.board) != preflop and o.legal.call_amount > 0)
    return obs, ObservationBuilder(cfg).build(obs)


def test_decision_context_facts_are_computed_from_public_info():
    obs, po = _first_decision(preflop=True)
    dc = decision_context(po)
    bb = obs.bb
    call = obs.legal.call_amount / bb
    assert dc.street == "preflop" and dc.decision_context_version == DECISION_CONTEXT_VERSION
    assert dc.to_call == pytest.approx(call)
    assert dc.required_equity == pytest.approx(call / (obs.pot / bb + call))
    assert dc.pot == pytest.approx(obs.pot / bb)
    assert dc.hole_cards == tuple(obs.hole_cards) and "call" in dc.legal_actions
    assert dc.hero_position in {"blinds", "early", "middle", "late"}
    obs2, po2 = _first_decision(preflop=False)
    dc2 = decision_context(po2)
    assert dc2.street in {"flop", "turn", "river"} and dc2.street_aggressor is None


def test_decision_context_fields_follow_tp_spec():
    fields = [f.name for f in dataclasses.fields(DecisionContext) if f.name != "decision_context_version"]
    s11 = (ROOT / "docs" / "TP.md").read_text(encoding="utf-8")
    assert f"DecisionContext v{DECISION_CONTEXT_VERSION}" in s11
    spec = pytest.importorskip("stalker.tp.spec")
    assert fields == spec.load().data["decision_context"]


def test_opp_range_label_respects_card_removal_and_the_assumed_policy():
    _, po = _first_decision(preflop=True)
    teacher = TeacherContext("t", "1", lambda cls, act: 1.0 if cls == "AA" or act != "cbr" else 0.0)
    slot = next(k for k, s in enumerate(po.seats) if s.used and k != 0 and s.in_hand)
    w = opp_range_label(po, teacher, slot)
    assert w.sum() == pytest.approx(1.0)
    dead = {card(c) for c in po.hole_cards}
    assert all(w[i] == 0 for i, (a, b) in enumerate(COMBOS) if a in dead or b in dead)


def test_gates_md_l7_matches_implementation():
    gates = (ROOT / "referee" / "GATES.md").read_text(encoding="utf-8")
    row = next(line for line in gates.splitlines() if line.startswith("| L7 |"))
    assert f"N={gate_l.L7_WORLDS}" in row and "check_l7" in row
