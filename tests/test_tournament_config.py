import json
from dataclasses import replace

import pytest

from stalker.tools import build_presets
from stalker.tournament import config as c
from stalker.tournament.config import BlindLevel, ConfigError, TournamentConfig

LV = (BlindLevel(25, 50, 0, 3), BlindLevel(50, 100, 0, 2), BlindLevel(100, 200, 0, 4))


def make(**kw):
    base = dict(name="t", players=6, table_size=6, starting_stack=1500, levels=LV, payouts=(1.0,))
    base.update(kw)
    return TournamentConfig(**base)


def test_json_roundtrip():
    cfg = make(payouts=(0.7, 0.3), buy_in=10)
    assert TournamentConfig.from_json(cfg.to_json()) == cfg
    assert json.loads(cfg.to_json())["schema_version"] == 1


def test_unknown_schema_version_rejected():
    d = make().to_dict()
    d["schema_version"] = 99
    with pytest.raises(ConfigError, match="schema_version"):
        TournamentConfig.from_dict(d)


@pytest.mark.parametrize("gen,expected", [
    (c.winner_take_all(), (1.0,)),
    (c.flat(4), (0.25,) * 4),
    (c.top_heavy(3, 2.0), (4 / 7, 2 / 7, 1 / 7)),
])
def test_simple_payout_generators(gen, expected):
    assert gen == pytest.approx(expected)
    assert sum(gen) == pytest.approx(1.0)


def test_mtt_payouts_paid_count_and_shape():
    p = c.mtt_payouts(180, 15)
    assert len(p) == 27
    assert sum(p) == pytest.approx(1.0)
    assert all(a > b for a, b in zip(p, p[1:]))
    assert len(c.mtt_payouts(2, 1)) == 1  # at least first place


def test_generator_errors():
    for bad in (lambda: c.flat(0), lambda: c.top_heavy(3, 0.5), lambda: c.mtt_payouts(10, 0)):
        with pytest.raises(ConfigError):
            bad()


@pytest.mark.parametrize("kw,msg", [
    (dict(players=1), "at least 2"),
    (dict(table_size=11), "between 2 and 10"),
    (dict(table_size=1), "between 2 and 10"),
    (dict(starting_stack=0), "positive"),
    (dict(starting_stack=1500.5), "integers"),
    (dict(payouts=(0.5, 0.3)), "sum"),
    (dict(payouts=(0.3, 0.7)), "non-increasing"),
    (dict(players=2, payouts=(0.5, 0.3, 0.2)), "exceed players"),
    (dict(payouts=()), "empty"),
    (dict(ante_mode="weird"), "ante_mode"),
    (dict(payout_mode="amount", payouts=(10.5,)), "integers"),
    (dict(levels=(BlindLevel(50, 100, 0, 3), BlindLevel(25, 50, 0, 3))), "monotonically"),
    (dict(levels=(BlindLevel(50, 100, 0, 3), BlindLevel(50, 100, 0, 3))), "monotonically"),
    (dict(levels=(BlindLevel(25, 50, 5, 3),)), "ante_mode='none'"),
    (dict(levels=(BlindLevel(100, 50, 0, 3),)), "exceeds bb"),
    (dict(levels=(BlindLevel(25.5, 50, 0, 3),)), "integers"),
    (dict(levels=()), "empty"),
])
def test_validation_errors(kw, msg):
    with pytest.raises(ConfigError, match=msg):
        make(**kw)


def test_amount_payouts():
    cfg = make(payout_mode="amount", payouts=(60, 40), buy_in=20)
    assert cfg.prize_pool == 100
    assert cfg.payout_ratios() == pytest.approx((0.6, 0.4))
    assert make(payouts=(0.7, 0.3), buy_in=10).payout_amounts() == pytest.approx((42, 18))


def test_level_at_and_next_level():
    cfg = make()  # level lengths 3, 2, 4 hands
    assert [cfg.level_at(h).bb for h in range(1, 11)] == [50] * 3 + [100] * 2 + [200] * 4 + [200]
    assert cfg.next_level(1) == LV[1]
    assert cfg.next_level(4) == LV[2]
    assert cfg.next_level(9) is None
    assert [cfg.hands_left_in_level(h) for h in (1, 3, 4, 5, 6)] == [3, 1, 2, 1, None]
    assert cfg.hands_left_in_level(100) is None
    with pytest.raises(ValueError):
        cfg.level_at(0)


def test_minutes_unit_uses_index_lookup():
    cfg = make(length_unit="minutes")
    assert cfg.level_index_at(0) == 0 and cfg.level_index_at(3) == 1
    with pytest.raises(ValueError, match="minutes"):
        cfg.level_at(1)


def test_presets_load_and_cover_required_set():
    names = c.preset_names()
    assert len(names) >= 6
    for n in names:
        cfg = c.load_preset(n)
        assert cfg.level_at(1).bb > 0
    assert c.load_preset("mtt180_bbante").ante_mode == "bb_ante"
    assert len(c.load_preset("mtt180_bbante").payouts) == 27
    assert c.load_preset("9max_sng_503020").payouts == (0.5, 0.3, 0.2)
    assert c.load_preset("6max_sng_wta").payouts == (1.0,)
    with pytest.raises(ConfigError, match="unknown preset"):
        c.load_preset("nope")


def test_committed_presets_match_generator():
    for key, conf in build_presets.build().items():
        assert c.load_preset(key) == conf, f"run: python -m stalker.tools.build_presets ({key})"


def test_replace_revalidates():
    with pytest.raises(ConfigError):
        replace(make(), players=1)
