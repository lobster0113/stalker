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
    assert by["self5"] == 0.0 and r["worst"]["name"] == "tag5"


def test_worst_ignores_the_all_self_configuration(monkeypatch):
    # A policy that beats every non-self table: self5 is 0.0 but must not be reported as the worst.
    def fake(target, opps, deal_seed, k=5, depth="basic"):
        return np.zeros(6) if all(o is target for o in opps) else np.full(6, 0.5)

    monkeypatch.setattr(F, "play_deal", fake)
    r = F.evaluate(F.uniform, 3, configs=["self5", "tag5", "nit5"])
    by = {c["name"]: c["bb100"] for c in r["configs"]}
    assert by["self5"] == 0.0 and by["tag5"] > 0
    assert r["worst"]["name"] in ("tag5", "nit5") and r["worst"]["bb100"] > 0
    only_self = F.evaluate(F.uniform, 3, configs=["self5"])
    assert only_self["worst"]["name"] == "self5"


def test_results_are_seeded():
    a = F.evaluate(F.uniform, 3, seed=5, configs=["lag5"])
    assert a == F.evaluate(F.uniform, 3, seed=5, configs=["lag5"])


@pytest.mark.slow
def test_uniform_play_loses_to_tight_and_aggressive_fields():
    r = F.evaluate(F.uniform, 150, seed=1, configs=["tag5", "nit5", "lag5"])
    for c in r["configs"]:
        assert c["ci95"][1] < 0, c
    assert r["worst"]["bb100"] == min(c["bb100"] for c in r["configs"])


def test_v2_adds_registered_champions_and_v1_still_loads():
    spec, sha = F.load()
    assert spec["version"] == 2 and F.load(F.CONFIGS_V1)[0]["version"] == 1 and sha != F.load(F.CONFIGS_V1)[1]
    champs = {o for c in spec["configs"] for o in c["opponents"] if o.startswith(F.CHAMPION)}
    assert len(champs) >= 2 and champs <= {F.CHAMPION + n for n in F.champion_names(spec)}
    c = F.champion("beginner-40783153094")
    assert (c.k, c.depth, c.menu, c.raise_cap, c.variant) == (5, "basic", "v1", G.RAISE_CAP, "")
    assert len(c.sha256) == 64 and c.policy


def test_unregistered_champion_and_tampered_file_are_rejected(tmp_path):
    spec, _ = F.load()
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({**spec, "configs": [{"name": "x", "opponents": ["champion:nobody"] * 5}]}),
                   encoding="utf-8")
    with pytest.raises(F.FieldError, match="unknown opponents"):
        F.load(bad)
    reg = json.loads((F.HERE / F.REGISTRY).read_text(encoding="utf-8"))
    entry = dict(reg["champions"][0], file=str(F.HERE / "champions" / reg["champions"][0]["file"]), sha256="0" * 64)
    fake = tmp_path / "reg.json"
    fake.write_text(json.dumps({"champions": [entry]}), encoding="utf-8")
    with pytest.raises(F.FieldError, match="sha256"):
        F.champion(entry["name"], str(fake))


def test_a_champion_reads_its_own_beliefs_like_the_same_policy_as_target():
    # The target is the champion's own table read the same way: every rotation plays the same hand -> zero.
    c = F.champion("beginner-40783153094")
    for d in range(3):
        assert F.play_deal(c.policy, [c] * 5, d, k=c.k, depth=c.depth).sum() == pytest.approx(0.0, abs=1e-9)


def test_a_champion_keeps_its_key_variant_under_the_targets():
    c = F.champion("beginner-40783153094")
    s = G.deal(np.random.default_rng(4), 6)
    ranges = F.K.initial_ranges(6)
    base = c.probs(s, s.to_act, ranges)
    with F.K.using_variant("s2"):
        assert np.array_equal(c.probs(s, s.to_act, ranges), base)


def test_rows_report_pairing_and_seat_mix_and_champion_hashes():
    r = F.evaluate(F.uniform, 2, configs=["mixed_styles", "champions_mixed"])
    by = {c["name"]: c for c in r["configs"]}
    mixed = by["champions_mixed"]
    assert mixed["hands"] == 12 and mixed["deals"] == 2 and mixed["ci95_low"] == mixed["ci95"][0]
    assert mixed["opponents"][0].startswith(F.CHAMPION) and sum(mixed["seat_mix"].values()) == 5
    assert by["mixed_styles"]["seat_mix"] == {"tag": 1, "lag": 1, "nit": 1, "calling_station": 1, "maniac": 1}
    assert set(r["champions"]) == {o[len(F.CHAMPION):] for o in mixed["opponents"]} and "duplicate" in r["pairing"]


def test_champion_configs_are_skipped_on_rules_they_were_not_trained_on():
    with G.rules("real", None):
        r = F.evaluate(F.uniform, 2, configs=["tag5", "champion_mid5"])
    assert [c["name"] for c in r["configs"]] == ["tag5"] and r["champions"] == {}
    assert r["skipped"][0]["name"] == "champion_mid5" and "menu v1" in r["skipped"][0]["reason"]
    with G.rules("real", None), pytest.raises(F.FieldError, match="skipped"):
        F.evaluate(F.uniform, 2, configs=["champion_mid5"])
