"""#426: E3 average-strategy accumulation rule (legacy vs own reach), checkpoints and parallel workers."""
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
               if n.startswith("e3-") and n not in ("e3-tp-mid-ownavg-w4", "e3-tp-mid-c1-w4"))


def test_ownavg_job_refuses_a_legacy_checkpoint(tmp_path):
    m = E3MCCFR(1, 5, 6)
    (tmp_path / "e3-tp-mid-ownavg-w4-seed1.ckpt.json").write_text(json.dumps(m.state()), encoding="utf-8")
    with pytest.raises(SystemExit, match="avg_rule 'legacy', not 'own'"):
        T.run("e3-tp-mid-ownavg-w4", 1, 1, tmp_path / "out", resume=tmp_path)
