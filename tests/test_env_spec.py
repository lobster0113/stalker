import dataclasses
import json

import pytest

from stalker.env import spec as S
from stalker.records.schema import SCHEMA_VERSION, GameRecord, migrate, to_dict
from stalker.records.store import RECORDS, MANIFEST, RunManifest, iter_records, run_env_id, write_manifest
from stalker.tournament.config import load_preset, preset_names


def _spec(**over) -> S.EnvSpec:
    return dataclasses.replace(S.from_tournament(load_preset("6max_sng_wta")), **over)


def test_env_id_is_deterministic_and_field_sensitive():
    a, b = _spec(), _spec()
    assert a.env_id == b.env_id and len(a.env_id) == 16 and int(a.env_id, 16) >= 0
    assert _spec(rake=1).env_id != a.env_id
    assert _spec(initial_stacks=(1501,) + a.initial_stacks[1:]).env_id != a.env_id


def test_env_id_ignores_field_order():
    a = _spec()
    shuffled = json.dumps(dict(reversed(list(json.loads(a.to_json()).items()))))
    assert S.EnvSpec.from_json(shuffled).env_id == a.env_id


def test_json_round_trip_and_registry(tmp_path):
    a = _spec()
    assert S.EnvSpec.from_json(a.to_json()) == a
    env_id = S.register(a, tmp_path)
    assert S.lookup(env_id, tmp_path) == a
    with pytest.raises(S.EnvSpecError, match="not registered"):
        S.lookup("0" * 16, tmp_path)
    (tmp_path / f"{env_id}.json").write_text(_spec(rake=5).to_json())
    with pytest.raises(S.EnvSpecError, match="edited"):
        S.lookup(env_id, tmp_path)


@pytest.mark.parametrize("name", preset_names())
def test_every_preset_has_a_registered_spec(name):
    spec = S.from_tournament(load_preset(name))
    assert S.lookup(spec.env_id) == spec, f"run: python -m stalker.env.spec  (registers {name})"


def test_e1_pushfold_specs_are_registered_and_distinct():
    ids = {S.pushfold(st, a).env_id for st in (1.0, 10.0, 15.0) for a in (0.0, 1.0)}
    assert len(ids) == 6
    assert all(S.lookup(i).kind == "hu_pushfold" for i in ids)


@pytest.mark.parametrize("over,msg", [
    ({"initial_stacks": (-5, 100)}, "positive integers"),
    ({"blind_schedule": (), "ante_schedule": ()}, "blind_schedule is empty"),
    ({"kind": "spin"}, "kind 'spin'"),
    ({"rake": -1}, "rake"),
    ({"table_size": 1}, "table_size"),
])
def test_invalid_specs_say_how_to_fix(over, msg):
    with pytest.raises(S.EnvSpecError, match=msg):
        _spec(**over)


def test_v1_records_migrate_with_the_run_env_id(tmp_path):
    cfg = load_preset("6max_sng_wta")
    write_manifest(tmp_path, dataclasses.replace(RunManifest.create("r", cfg, 1, "v"), schema_version=1))
    env_id = S.from_tournament(cfg).env_id
    game = GameRecord("ep", "g", "t", 1.0, (1, 2), (2.0, 0.0), (1.0, -1.0), 10, env_id)
    v1 = {k: v for k, v in to_dict(game).items() if k != "env_id"}
    v1["schema_version"] = 1
    (tmp_path / RECORDS).write_text(json.dumps({"type": "game", "record": v1}) + "\n")
    (rec,) = list(iter_records(tmp_path))
    assert rec == game and rec.schema_version == SCHEMA_VERSION == 2
    assert run_env_id(tmp_path) == env_id


def test_migrate_decision_ids_and_rejects_unknown_versions():
    d = migrate("decision", {"schema_version": 1, "ids": {"game_id": "g"}}, "0123456789abcdef")
    assert d["ids"]["env_id"] == "0123456789abcdef" and d["schema_version"] == 2
    with pytest.raises(ValueError, match="no migration"):
        migrate("game", {"schema_version": 0}, "0123456789abcdef")


def test_generated_records_carry_the_config_env_id(tmp_path):
    from stalker.pipeline.generate import generate

    cfg = load_preset("6max_sng_wta")
    generate(cfg, 1, 3, tmp_path)
    ids = {r.ids.env_id if hasattr(r, "ids") else r.env_id for r in iter_records(tmp_path)}
    assert ids == {S.from_tournament(cfg).env_id}
    assert (tmp_path / MANIFEST).exists()
