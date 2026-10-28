import json

import numpy as np
import pytest

from referee.e3 import field as F
from stalker.e3 import game as G
from stalker.e3 import personas


def test_config_set_loads_with_hash_and_covers_the_registered_kinds():
    spec, sha = F.load()
    assert len(sha) == 64 and spec["players"] == 6
    names = {c["name"] for c in spec["configs"]}
    assert {"self5", "uniform5", "mixed_styles"} <= names and len(names) == len(spec["configs"])


def test_bad_config_files_are_rejected(tmp_path):
    spec, _ = F.load()
    short = tmp_path / "short.json"
    short.write_text(json.dumps({**spec, "configs": [{"name": "x", "opponents": ["tag"] * 4}]}), encoding="utf-8")
    with pytest.raises(F.FieldError, match="need 5"):
        F.load(short)
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps({**spec, "configs": [{"name": "x", "opponents": ["shark"] * 5}]}), encoding="utf-8")
    with pytest.raises(F.FieldError, match="unknown opponents"):
        F.load(unknown)


def test_personas_return_distributions_over_the_e3_menu():
    rng = np.random.default_rng(3)
    field = personas.field()
    for _ in range(30):
        s = G.deal(rng, 6)
        while not s.done:
            p = field[s.to_act % len(field)](s)
            assert len(p) == len(G.legal(s)) and abs(p.sum() - 1) < 1e-12 and (p >= 0).all()
            s = G.apply(s, G.legal(s)[int(rng.choice(len(p), p=p))])


def test_a_table_of_one_policy_sums_to_zero_on_every_deal():
    # Duplicate symmetry: same policy everywhere -> the same hand in every rotation -> net zero.
    tag = personas.Persona("tag")
    for d in range(5):
        assert F.play_deal(tag, [tag] * 5, d).sum() == pytest.approx(0.0, abs=1e-9)
    assert F.evaluate(F.uniform, 4, configs=["self5"])["configs"][0]["bb100"] == 0.0


def test_tp_policy_self_table_is_zero_and_beliefs_do_not_break_play():
    pol = {}  # an empty TP table plays uniformly but still tracks its public ranges
    r = F.evaluate(pol, 3, configs=["self5", "tag5"])
    by = {c["name"]: c["bb100"] for c in r["configs"]}
    assert by["self5"] == 0.0 and r["worst"]["name"] == min(by, key=by.get)


def test_results_are_seeded():
    a = F.evaluate(F.uniform, 3, seed=5, configs=["lag5"])
    assert a == F.evaluate(F.uniform, 3, seed=5, configs=["lag5"])


@pytest.mark.slow
def test_uniform_play_loses_to_tight_and_aggressive_fields():
    r = F.evaluate(F.uniform, 150, seed=1, configs=["tag5", "nit5", "lag5"])
    for c in r["configs"]:
        assert c["ci95"][1] < 0, c
    assert r["worst"]["bb100"] == min(c["bb100"] for c in r["configs"])
