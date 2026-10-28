import numpy as np

from stalker.e2.abstraction import TIERS
from stalker.e2.field import FieldMCCFR
from stalker.e2.mccfr import MCCFR


def test_empty_field_is_plain_self_play():
    a, b = FieldMCCFR(3, TIERS["beginner"], field_tiers=()), MCCFR(3, TIERS["beginner"])
    a.iterate(40)
    b.iterate(40)
    assert a.policy() == b.policy()


def test_field_play_is_deterministic_and_changes_the_policy():
    a, b, c = (FieldMCCFR(2, TIERS["beginner"]) for _ in range(3))
    for m in (a, b):
        m.iterate(30)
    c.iterate(30)
    assert a.policy() == b.policy() and len(a.policy()) > 20
    assert all(abs(sum(v) - 1) < 1e-9 for v in a.policy().values())
    self_play = MCCFR(2, TIERS["beginner"])
    self_play.iterate(30)
    assert a.policy() != self_play.policy()


def test_field_members_learn_too():
    m = FieldMCCFR(1, TIERS["beginner"])
    m.iterate(40)
    assert all(f.regret and f.policy() for f in m.field)
    assert len(m.field) == 3
