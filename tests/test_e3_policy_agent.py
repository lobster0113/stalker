"""E3 policy as a tournament agent (#900): c1 key, backoff counts, determinism, icm_grid policy agents."""
from __future__ import annotations

import json

import numpy as np
import pytest

from stalker.agents.e3_policy import (
    BackoffError,
    E3PolicyAgent,
    PolicyTable,
    e3_stage,
    load_table,
)
from stalker.tools.icm_grid import run_grid
from stalker.tournament.config import load_preset
from stalker.tournament.director import run_game
from stalker.tournament.start_state import make_start_state

PRESET = "9max_sng_503020"
EMPTY = PolicyTable({}, k=5, depth="basic", menu="v1", raise_cap=3)


class Recorder(E3PolicyAgent):
    """Records the c1 key (and legal-action count) of every decision it could mirror."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.keys: list[tuple[str, int]] = []

    def _policy_act(self, obs):
        try:
            key = self.decision_key(obs)
        except BackoffError:
            pass
        else:
            from stalker.e3 import game as G
            self.keys.append((key, len(G.legal(self._mirror["s"]))))
        return super()._policy_act(obs)


def play(table, remaining=4, seed=0, cls=E3PolicyAgent, profile="even"):
    cfg = load_preset(PRESET)
    ss = make_start_state(cfg, np.random.default_rng([seed, 1]), remaining, profile, 0)
    agents = [cls(table, np.random.default_rng([seed, 2, i]), players=cfg.players, table_size=cfg.table_size)
              for i in range(cfg.players)]
    res = run_game(cfg, agents, np.random.default_rng([seed, 3]), start_state=ss)
    return res, agents


def test_e3_stage_follows_adr_0027_decision_2():
    assert [e3_stage(r, 3) for r in (9, 5, 4, 3, 2, 1)] == ["e", "e", "b", "m", "m", "m"]
    assert e3_stage(9, 27, players=180, table_size=9) == "f"    # MTT final table in the money
    assert e3_stage(20, 27, players=180, table_size=9) == "m"
    assert e3_stage(28, 27, players=180, table_size=9) == "b"
    assert e3_stage(3, 3, players=9, table_size=9) == "m"       # a SNG has no final table


@pytest.mark.parametrize("remaining,env,n", [(4, "tb0", "n4"), (3, "tm0", "n3")])
def test_decision_key_reads_survivors_stage_and_ante(remaining, env, n):
    _, agents = play(EMPTY, remaining, cls=Recorder)
    keys = [k for a in agents for k, _ in a.keys if not k.startswith("call|")]
    assert keys
    first = keys[0].split("|")
    assert first[1] == n and env in first   # basic key: b|n<players>|...|t<stage><ante>|...


def test_missing_key_backs_off_to_rule_bot_and_counts():
    res, agents = play(EMPTY)
    assert res.illegal_actions == 0
    c = [a.counts() for a in agents]
    assert sum(x["decisions"] for x in c) > 0
    assert all(x["policy_hits"] == 0 and x["backoffs"] == x["decisions"] for x in c)
    assert sum(x["backoff_reasons"].get("no_key", 0) for x in c) > 0


@pytest.fixture(scope="module")
def table():
    """Uniform rows for every key an all-backoff game reached: the replay of the same seeds hits them."""
    _, agents = play(EMPTY, cls=Recorder)
    rows = {k: [1.0 / m] * m for a in agents for k, m in a.keys}
    return PolicyTable(rows, k=5, depth="basic", menu="v1", raise_cap=3)


@pytest.mark.slow
def test_policy_rows_are_played_and_counted(table):
    res, agents = play(table)
    c = [a.counts() for a in agents]
    hits = sum(x["policy_hits"] for x in c)
    assert hits > 0
    assert all(x["policy_hits"] + x["backoffs"] == x["decisions"] for x in c)
    assert res.illegal_actions == 0


@pytest.mark.slow
def test_same_seed_same_game_result(table):
    a, ag_a = play(table, seed=0)
    b, ag_b = play(table, seed=0)
    assert a == b
    assert [x.counts() for x in ag_a] == [x.counts() for x in ag_b]
    assert sum(x.counts()["policy_hits"] for x in ag_a) > 0


def test_load_table_web_file_and_folder(tmp_path, table):
    doc = {"q": 1000, "k": table.k, "depth": table.depth, "menu": "v1", "raise_cap": 3, "key_variant": "c1",
           "policy": {k: [round(x * 1000) for x in row] for k, row in table.policy.items()}}
    (tmp_path / "beginner-4.json").write_text(json.dumps(doc), encoding="utf-8")
    loaded = load_table(tmp_path)
    assert loaded.policy.keys() == table.policy.keys() and (loaded.k, loaded.depth) == (5, "basic")
    (tmp_path / "other.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        load_table(tmp_path)
    with pytest.raises(FileNotFoundError):
        load_table(tmp_path / "missing.json")


@pytest.mark.slow
def test_icm_grid_policy_agents_report_backoff(tmp_path, table):
    doc = {"q": 1000, "k": table.k, "depth": table.depth, "menu": "v1", "raise_cap": 3,
           "policy": {k: [round(x * 1000) for x in row] for k, row in table.policy.items()}}
    path = tmp_path / "p.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    grid = run_grid([PRESET], [4], ["even"], games=1, seed=0, agents=f"policy:{path}")
    assert grid["agents"] == f"policy:{path}"
    (cell,) = grid["cells"]
    pol = cell["policy"]
    assert pol["decisions"] > 0 and pol["policy_hits"] + pol["backoffs"] == pol["decisions"]
    assert pol["backoff_rate"] == pytest.approx(pol["backoffs"] / pol["decisions"])
    again = run_grid([PRESET], [4], ["even"], games=1, seed=0, agents=f"policy:{path}")
    assert again == grid


@pytest.mark.slow
def test_small_trained_policy_finishes_ten_bubble_games():
    from stalker.e3.mccfr import E3MCCFR

    m = E3MCCFR(seed=1, k=5, n=4, depth="basic", key_variant="c1", stacks="sampled", payoff="icm",
                payouts=(0.5, 0.3, 0.2), stage="b")
    m.iterate(3)
    table = PolicyTable.from_model(m)
    for g in range(10):
        res, agents = play(table, seed=g, profile="random")
        assert sorted(res.ranks) == list(range(1, 10))
        assert all(a.counts()["decisions"] == a.counts()["policy_hits"] + a.counts()["backoffs"] for a in agents)
