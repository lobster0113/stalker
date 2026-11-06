"""#426: E3 average-strategy accumulation rule (legacy vs own reach), checkpoints and parallel workers."""
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pytest

from stalker import train_jobs as T
from stalker.e3 import parallel
from stalker.e3.mccfr import E3MCCFR


def _tables_equal(a: dict, b: dict) -> bool:
    return a.keys() == b.keys() and all(np.array_equal(a[k], b[k]) for k in a)


@pytest.fixture(scope="module")
def pool():
    with ProcessPoolExecutor(2) as p:
        yield p


def test_heads_up_rules_are_bit_identical():
    # Heads-up there is no other non-traverser to divide out, so "own" is the legacy update exactly.
    a, b = E3MCCFR(4, 3, 2), E3MCCFR(4, 3, 2, avg_rule="own")
    a.iterate(6)
    b.iterate(6)
    sa, sb = a.state(), b.state()
    assert (sa.pop("version"), sa.pop("avg_rule"), sb.pop("version"), sb.pop("avg_rule")) == (1, "legacy", 3, "own")
    assert json.dumps(sa, sort_keys=True) == json.dumps(sb, sort_keys=True)


def test_three_handed_own_rule_changes_only_the_average():
    # The rule reads no random numbers and no regrets, so both chains sample the same hands and regrets.
    a, b = E3MCCFR(4, 3, 3), E3MCCFR(4, 3, 3, avg_rule="own")
    a.iterate(6)
    b.iterate(6)
    assert _tables_equal(a.regret, b.regret) and a.rng.bit_generator.state == b.rng.bit_generator.state
    assert a.avg.keys() == b.avg.keys()
    assert not _tables_equal(dict(a.avg), dict(b.avg))
    # each visit is reweighted by a positive scalar: every row stays a positive sum of sigmas
    assert all((v >= 0).all() and v.sum() > 0 for v in b.avg.values())


def test_six_max_job_table_and_sampling_do_not_depend_on_the_rule(pool):
    # #426 CI: one seed-2 run of e3-tp-mid-ownavg-w4 ended with another table than e3-tp-mid-w4, and a rerun of
    # the same commit matched it again; the rule itself must never be the cause. Same tier, seat count, seed
    # and parallel path as the jobs (locally the two stayed identical through 18k iterations of seed 2).
    from stalker.e3.tp_key import TIER_DEPTH, TIER_K

    a, b = (E3MCCFR(2, TIER_K["mid"], 6, TIER_DEPTH["mid"], "v1", 3, avg_rule=r) for r in ("legacy", "own"))
    for m in (a, b):
        parallel.iterate(m, 16, workers=2, batch=4, pool=pool)
    assert _tables_equal(a.regret, b.regret) and a.rng.bit_generator.state == b.rng.bit_generator.state
    assert a.visits == b.visits and a.nodes == b.nodes and not _tables_equal(dict(a.avg), dict(b.avg))


def test_unknown_avg_rule_is_refused():
    with pytest.raises(ValueError, match="avg_rule"):
        E3MCCFR(0, 3, 3, avg_rule="x")


def test_own_checkpoint_continues_bit_for_bit():
    whole = E3MCCFR(5, 3, 3, avg_rule="own")
    whole.iterate(6)
    part = E3MCCFR(5, 3, 3, avg_rule="own")
    part.iterate(3)
    st = json.loads(json.dumps(part.state()))
    assert (st["version"], st["avg_rule"]) == (3, "own")
    part = E3MCCFR.from_state(st, "own")
    part.iterate(3)
    assert part.state() == whole.state()


def test_old_checkpoint_loads_as_legacy_and_rules_never_mix():
    m = E3MCCFR(5, 3, 3)
    m.iterate(2)
    old = json.loads(json.dumps(m.state()))
    del old["avg_rule"]                     # a checkpoint written before #426
    assert E3MCCFR.from_state(old).avg_rule == "legacy" == E3MCCFR.from_state(old, "legacy").avg_rule
    with pytest.raises(ValueError, match="avg_rule 'legacy', not 'own'"):
        E3MCCFR.from_state(old, "own")
    own = E3MCCFR(5, 3, 3, avg_rule="own").state()
    with pytest.raises(ValueError, match="avg_rule 'own', not 'legacy'"):
        E3MCCFR.from_state(own, "legacy")
    # code before #426 reads version 1 only, so an "own" checkpoint must never be written as version 1
    for bad in ({**own, "version": 1}, {**old, "version": 3}):
        with pytest.raises(ValueError, match="version"):
            E3MCCFR.from_state(bad)


def test_own_rule_with_average_ranges_checkpoints_both():
    # #405 and #426 together: version 3 (own) still carries the range snapshot, and resumes bit for bit
    whole = E3MCCFR(5, 3, 3, ranges="average", range_every=2, avg_rule="own")
    whole.iterate(6)
    part = E3MCCFR(5, 3, 3, ranges="average", range_every=2, avg_rule="own")
    part.iterate(3)
    st = json.loads(json.dumps(part.state()))
    assert (st["version"], st["avg_rule"], st["ranges"]) == (3, "own", "average") and st["snap"]
    part = E3MCCFR.from_state(st, "own")
    part.iterate(3)
    assert part.state() == whole.state()


def test_one_worker_is_the_sequential_own_chain():
    a, b = E3MCCFR(3, 3, 3, avg_rule="own"), E3MCCFR(3, 3, 3, avg_rule="own")
    a.iterate(4)
    parallel.iterate(b, 4, workers=1)
    assert a.state() == b.state()


def test_workers_accumulate_with_the_models_rule(pool):
    a, b = E3MCCFR(6, 3, 3), E3MCCFR(6, 3, 3, avg_rule="own")
    parallel.iterate(a, 4, workers=2, batch=1, pool=pool)
    parallel.iterate(b, 4, workers=2, batch=1, pool=pool)
    assert _tables_equal(a.regret, b.regret) and not _tables_equal(dict(a.avg), dict(b.avg))
    c = E3MCCFR(6, 3, 3, avg_rule="own")
    parallel.iterate(c, 4, workers=2, batch=1, pool=pool)
    assert c.state() == b.state()


def test_ownavg_job_is_registered_and_existing_jobs_stay_legacy():
    job = T.JOBS["e3-tp-mid-ownavg-w4"]
    assert "e3-tp-mid-ownavg-w4" in T.RESUMABLE
    assert job.keywords == {"tier": "mid", "name": "e3-tp-mid-ownavg-w4", "workers": 4, "avg_rule": "own"}
    # jobs added after #426 may choose own reach: the combined-key job does (#400)
    assert T.JOBS["e3-tp-mid-c1-w4"].keywords["avg_rule"] == "own"
    assert all(j.keywords.get("avg_rule", "legacy") == "legacy" for n, j in T.JOBS.items()
               if n.startswith("e3-") and n not in ("e3-tp-mid-ownavg-w4", "e3-tp-mid-c1-w4",
                                                    "e3-tp-mid-ownavg-cap2-w4", "e3-tp-mid-ownavg-cap8-w4")
                   and not n.endswith("-w4-eval"))


def test_ownavg_job_refuses_a_legacy_checkpoint(tmp_path):
    m = E3MCCFR(1, 5, 6)
    (tmp_path / "e3-tp-mid-ownavg-w4-seed1.ckpt.json").write_text(json.dumps(m.state()), encoding="utf-8")
    with pytest.raises(SystemExit, match="avg_rule 'legacy', not 'own'"):
        T.run("e3-tp-mid-ownavg-w4", 1, 1, tmp_path / "out", resume=tmp_path)


# --- #448: avg_cap clips the own-reach weight --------------------------------------------------------------

def _state(m, n):
    m.iterate(n)
    return json.loads(json.dumps(m.state()))


def test_no_cap_average_matches_the_hash_computed_on_main():
    # constant from origin/main at 2adf7ae (before avg_cap): `t / prod`, not `t * (1 / prod)`, which moved 368/1850 keys 1 ulp (#523)
    m = E3MCCFR(5, 3, 3, avg_rule="own")
    m.iterate(8)
    h = hashlib.sha256()
    for k in sorted(m.avg):
        h.update(k.encode() + b"\0" + m.avg[k].astype("<f8").tobytes())
    assert h.hexdigest() == "04a45996ade0896b5bbad9a1a673bf95e56e229eae2dd48e2533d22fafd370cb"


def test_no_cap_checkpoint_is_unchanged_and_a_huge_cap_is_no_cap():
    a, b, c = (E3MCCFR(5, 3, 3, avg_rule="own", avg_cap=cap) for cap in (None, 1e300, 1.0))
    sa, sb, sc = _state(a, 5), _state(b, 5), _state(c, 5)
    assert "avg_cap" not in sa and sa["version"] == 3     # default: same checkpoint as before #448
    assert sb["regret"] == sa["regret"]   # a cap path multiplies t*(1/prod), 1 ulp off t/prod: close, not equal
    assert sb["avg"].keys() == sa["avg"].keys() and all(np.allclose(sb["avg"][k], sa["avg"][k], rtol=1e-12) for k in sa["avg"])
    assert sc["regret"] == sa["regret"] and sc["avg"] != sa["avg"]   # the cap moves only the average


def test_cap_checkpoint_is_version_8_continues_bit_for_bit_and_refuses_other_caps():
    whole = E3MCCFR(5, 3, 3, avg_rule="own", avg_cap=2.0)
    whole.iterate(6)
    part = E3MCCFR(5, 3, 3, avg_rule="own", avg_cap=2.0)
    st = _state(part, 3)
    assert (st["version"], st["avg_cap"]) == (8, 2.0)
    part = E3MCCFR.from_state(st, "own", avg_cap=2.0)
    part.iterate(3)
    assert part.state() == whole.state()
    assert E3MCCFR.from_state(st).avg_cap == 2.0
    with pytest.raises(ValueError, match="avg_cap"):
        E3MCCFR.from_state(st, "own", avg_cap=8.0)
    with pytest.raises(ValueError, match="avg_cap"):
        E3MCCFR.from_state({**st, "version": 3})
    plain = _state(E3MCCFR(5, 3, 3, avg_rule="own"), 2)
    with pytest.raises(ValueError, match="avg_cap"):
        E3MCCFR.from_state(plain, "own", avg_cap=2.0)


def test_cap_needs_the_own_rule_and_a_cap_of_at_least_one():
    for kw in ({"avg_rule": "legacy", "avg_cap": 2.0}, {"avg_rule": "own", "avg_cap": 0.5}):
        with pytest.raises(ValueError, match="avg_cap"):
            E3MCCFR(0, 3, 3, **kw)


def test_cap_keeps_every_other_checkpoint_field_in_version_8():
    m = E3MCCFR(5, 3, 3, ranges="average", range_every=2, avg_rule="own", avg_cap=2.0, key_variant="b1",
                stacks="sampled", player_mix=(2, 3))
    st = _state(m, 3)
    back = E3MCCFR.from_state(st)
    assert (back.ranges, back.key_variant, back.stacks, back.player_mix, back.avg_cap) == (
        "average", "b1", "sampled", (2, 3), 2.0)


def test_parallel_workers_apply_the_cap(pool):
    a, b = (E3MCCFR(7, 3, 3, avg_rule="own", avg_cap=cap) for cap in (None, 1.0))
    parallel.iterate(a, 4, workers=2, batch=1, pool=pool)
    parallel.iterate(b, 4, workers=2, batch=1, pool=pool)
    assert not _tables_equal(a.avg, b.avg)
    c = E3MCCFR(7, 3, 3, avg_rule="own", avg_cap=1.0)
    parallel.iterate(c, 4, workers=2, batch=1, pool=pool)
    assert c.state() == b.state()


def test_cap_jobs_are_registered_resumable_and_differ_from_ownavg_only_in_the_cap():
    base = T.JOBS["e3-tp-mid-ownavg-w4"].keywords
    for name, cap in (("e3-tp-mid-ownavg-cap2-w4", 2.0), ("e3-tp-mid-ownavg-cap8-w4", 8.0)):
        kw = T.JOBS[name].keywords
        assert name in T.RESUMABLE and kw["avg_cap"] == cap
        assert {k: v for k, v in kw.items() if k not in ("avg_cap", "name")} == {k: v for k, v in base.items() if k != "name"}
