"""#535: a player-mix run counts hands, traverser updates and c1 keys per player count, across resumes."""
import copy
import hashlib
import json

import pytest

from stalker import train_jobs as T
from stalker.e3 import parallel
from stalker.e3.mccfr import E3MCCFR, key_players
from stalker.tools import pod_train as P

MIX = (2, 3, 6)
AT = (3, 4, 5, 9, 12)   # the iteration counts the tests start from (`c1_at`)


def _c1(seed=3, **kw):
    return E3MCCFR(seed, 5, 6, "basic", key_variant="c1", player_mix=MIX, **kw)


@pytest.fixture(scope="module")
def c1_at():
    """`c1_at(n)`: a copy of `_c1()` after `iterate(n)`. One run is advanced and snapshotted instead of a fresh run per
    test (#826): consecutive `iterate` calls end in the same state, rng included, as one call of the total."""
    snaps: dict = {}

    def at(n):
        if n not in snaps:
            base = max((k for k in snaps if k < n), default=None)
            m = copy.deepcopy(snaps[base]) if base is not None else _c1()
            for stop in sorted({*(k for k in AT if m.iterations < k < n), n}):   # keep the counts passed on the way
                m.iterate(stop - m.iterations)
                snaps[stop] = copy.deepcopy(m)
        return copy.deepcopy(snaps[n])
    return at


def _state_digest(m) -> str:
    st = m.state()
    st.pop("rng")
    st.pop("chain")   # #712 adds the run history; the table and the older keys are what this pins
    return hashlib.sha256(json.dumps(st, sort_keys=True).encode()).hexdigest()[:16]


@pytest.mark.parametrize("args, kw, regret, state", [
    ((1, 5, 6, "basic"), {}, "ffb49dca274d3cd9b6ff0d58ea7436c1a517b19a5674f9c31bec51f0c382e08c", "0be7990aef720bd9"),
    ((2, 11, 3, "full"), {"avg_rule": "own", "key_variant": "c1"},
     "ebb0b43db24846e48d7e9cf820a1fa6ac69d1a0ab637e13257db2dadeb7ffb0d", "9319a647fedcfd29"),
])
def test_runs_without_player_mix_keep_their_table_and_checkpoint(args, kw, regret, state):
    # values from main before #535 (e7327b3): no counts are kept or saved for n-handed deals
    m = E3MCCFR(*args, **kw)
    m.iterate(3)
    assert m.regret_hash() == regret and _state_digest(m) == state
    assert "mix_counts" not in m.state() and m.mix_hands == {}


def test_counting_draws_no_random_numbers(c1_at):
    m = c1_at(3)   # the same mixed run on main before #535 (e7327b3)
    assert m.regret_hash() == "28b71e994f91658402bf11f0895a4a99307f773397adf5592d17eae2f5a840ae"


def test_per_size_counts_add_up_to_the_run(c1_at):
    m = c1_at(12)
    c = m.mix_counts()
    assert set(c) == {"2", "3", "6"}
    assert sum(r["hands"] for r in c.values()) == m.iterations == 12
    assert sum(r["visits"] for r in c.values()) == sum(m.visits.values())
    assert sum(r["keys"] for r in c.values()) + m.shared_keys() == len(m.regret)
    assert all(key_players(k) == (None if k.startswith("call|") else int(k.split("|")[1][1:])) for k in m.regret)
    assert m.shared_keys() == sum(k.startswith("call|") for k in m.regret)


def test_keys_are_not_split_for_keys_without_a_player_count():
    m = E3MCCFR(1, 5, 6, "basic", player_mix=(2, 3))
    m.iterate(4)
    assert all(r["keys"] is None for r in m.mix_counts().values()) and m.shared_keys() is None
    assert sum(r["hands"] for r in m.mix_counts().values()) == 4


def test_key_players_reads_every_depth():
    assert key_players("BTN|n3|0|2|1|0|2|0|tc0|s6:6|u02|ha|fcra|e0") == 3
    assert key_players("b|n2|late|0|2|1|2|tc0|s6:6|u02|ha|fcra|e0") == 2
    assert key_players("p|SB|n5|1|1|0|1|2|3|tc0|s6:6|u02|hn|kb|e3|n1|f0") == 5
    assert key_players("call|1|2|4|fc|e0") is None


def test_checkpoint_resume_counts_as_one_run(c1_at):
    once = c1_at(9)
    part = c1_at(5)
    st = json.loads(json.dumps(part.state()))
    assert st["version"] == 7 and st["counted_from"] == 0
    back = E3MCCFR.from_state(st, player_mix=MIX)
    back.iterate(4)
    assert back.regret_hash() == once.regret_hash()
    assert back.mix_counts() == once.mix_counts() and back.counted_from == 0


def test_version_6_checkpoint_counts_from_where_it_resumes(c1_at):
    m = c1_at(4)
    st = json.loads(json.dumps(m.state()))
    del st["mix_counts"], st["counted_from"]
    back = E3MCCFR.from_state({**st, "version": 6})
    assert back.counted_from == 4 and all(r["hands"] == r["visits"] == 0 for r in back.mix_counts().values())
    back.iterate(3)
    assert sum(r["hands"] for r in back.mix_counts().values()) == back.iterations - back.counted_from == 3
    m.iterate(3)
    assert back.regret_hash() == m.regret_hash()
    with pytest.raises(ValueError, match="version 6 or 7"):
        E3MCCFR.from_state({**st, "version": 5})


@pytest.mark.slow
def test_parallel_workers_add_their_counts():
    m = _c1()
    parallel.iterate(m, 6, workers=2, batch=2)
    c = m.mix_counts()
    assert sum(r["hands"] for r in c.values()) == m.iterations == 6
    assert sum(r["visits"] for r in c.values()) == sum(m.visits.values())


def test_pod_checkpoint_carries_the_counts(c1_at):
    m = c1_at(5)
    meta = {"k": m.k, "n": m.n, "depth": m.depth, "iterations": m.iterations, "nodes": m.nodes,
            "menu": m.menu, "raise_cap": m.raise_cap, "avg_rule": m.avg_rule, "rng": m.rng.bit_generator.state,
            "key_variant": m.key_variant, "stacks": m.stacks, "key_version": 1, "player_mix": list(MIX),
            **m._count_state()}
    back = E3MCCFR.from_state(P.unpack_state(P.pack(m), meta), player_mix=MIX)
    assert back.mix_counts() == m.mix_counts()
    meta6 = {k: v for k, v in meta.items() if k not in ("mix_counts", "counted_from")}
    st6 = P.unpack_state(P.pack(m), meta6)   # a pod result from before #535
    assert st6["version"] == 6 and E3MCCFR.from_state(st6).counted_from == 5


@pytest.fixture
def small(monkeypatch):
    for name in ("E3_LBR_HANDS", "E3_FIELD_HANDS", "E3_BY_PLAYERS_LBR_HANDS", "E3_BY_PLAYERS_FIELD_HANDS"):
        monkeypatch.setattr(T, name, 2)
    monkeypatch.setattr(T, "E3_BY_PLAYERS_LBR_HANDS_BY_N", {})


@pytest.mark.slow  # ~12-18s of quick (#816/#832); full/G1 still runs it
def test_result_and_summary_carry_the_counts(small, tmp_path):
    runs = []
    for seed in (1, 2):
        m = E3MCCFR(seed, 5, 3, "basic", key_variant="c1", player_mix=(2, 3))
        m.iterate(4)
        r = {"seed": seed, "iters": m.iterations, "iters_per_s": 1.0, **T.e3_evaluate(m, seed)}
        assert sum(r["by_players"][n]["hands"] for n in ("2", "3")) == 4
        assert r["by_players_counted_from"] == 0 and r["by_players_shared_keys"] == m.shared_keys()
        (tmp_path / f"e3-tp-x-seed{seed}.json").write_text(json.dumps(r), encoding="utf-8")
        runs.append(r)
    s = T.summarize("e3-tp-x", tmp_path)
    assert [sum(c["hands"] for c in row.values()) for row in s["by_players_counts_by_seed"]] == [4, 4]
    assert s["by_players_counts_by_seed"][0]["2"] == {c: runs[0]["by_players"]["2"][c] for c in ("hands", "visits", "keys")}
    assert s["by_players_counted_from_by_seed"] == [0, 0]
    assert s["by_players_shared_keys_by_seed"] == [r["by_players_shared_keys"] for r in runs]
