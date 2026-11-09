"""#712: a checkpoint records the runs it went through and the RNG hash at each seam."""
import json

import pytest

from stalker.e3.mccfr import E3MCCFR


def _roundtrip(m):
    return E3MCCFR.from_state(json.loads(json.dumps(m.state())))


def test_chain_grows_one_entry_per_resumed_run(monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "11")
    m = E3MCCFR(3, 5, 3, "basic")
    m.iterate(2)
    saved = json.loads(json.dumps(m.state()))   # the run id is read when the checkpoint is written
    assert [(c["run_id"], c["from_iters"], c["to_iters"]) for c in saved["chain"]] == [("11", 0, 2)]
    monkeypatch.setenv("GITHUB_RUN_ID", "22")
    m = E3MCCFR.from_state(saved)
    m.iterate(3)
    ch = m.state()["chain"]
    assert [(c["run_id"], c["from_iters"], c["to_iters"]) for c in ch] == [("11", 0, 2), ("22", 2, 5)]
    assert all(len(c["rng_sha256"]) == 64 for c in ch)


def test_run_id_is_null_outside_ci(monkeypatch):
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    m = E3MCCFR(3, 5, 3, "basic")
    m.iterate(1)
    assert m.state()["chain"][0]["run_id"] is None


def test_changed_rng_state_is_refused():
    m = E3MCCFR(3, 5, 3, "basic")
    m.iterate(2)
    st = json.loads(json.dumps(m.state()))
    st["rng"]["state"]["state"] += 1
    with pytest.raises(ValueError, match="RNG state does not match"):
        E3MCCFR.from_state(st)


def test_checkpoint_without_chain_or_hash_still_resumes():
    m = E3MCCFR(3, 5, 3, "basic")
    m.iterate(2)
    st = json.loads(json.dumps(m.state()))
    del st["chain"]
    old = E3MCCFR.from_state(st)
    assert old.chain == []
    old.iterate(1)
    assert [(c["from_iters"], c["to_iters"]) for c in old.state()["chain"]] == [(2, 3)]
    st = json.loads(json.dumps(m.state()))
    st["chain"][0]["rng_sha256"] = None
    st["rng"]["state"]["state"] += 1
    E3MCCFR.from_state(st)   # no hash to check against


def test_resumed_table_matches_one_uninterrupted_run():
    whole = E3MCCFR(4, 5, 3, "basic")
    whole.iterate(5)
    part = E3MCCFR(4, 5, 3, "basic")
    part.iterate(2)
    part = _roundtrip(part)
    part.iterate(3)
    assert part.regret_hash() == whole.regret_hash()
