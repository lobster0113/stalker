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


def test_backoff_reason_splits_no_key_from_arity_mismatch(table):
    """#961: a key missing from the table is `no_key`; a row of the wrong length is `arity_mismatch`."""
    _, agents = play(EMPTY, cls=Recorder)
    key, m = next((k, m) for a in agents for k, m in a.keys)
    bad = PolicyTable({key: [1.0 / (m + 1)] * (m + 1)}, k=5, depth="basic", menu="v1", raise_cap=3)
    _, ag = play(bad)
    reasons = {}
    for a in ag:
        for r, n in a.counts()["backoff_reasons"].items():
            reasons[r] = reasons.get(r, 0) + n
    assert reasons.get("arity_mismatch", 0) > 0
    assert reasons.get("no_key", 0) > 0   # other keys are still absent


def test_by_street_sums_to_totals_and_keeps_old_keys():
    _, agents = play(EMPTY)
    for a in agents:
        c = a.counts()
        assert sum(v["decisions"] for v in c["by_street"].values()) == c["decisions"]
        assert sum(v["policy_hits"] for v in c["by_street"].values()) == c["policy_hits"]
        assert {"decisions", "policy_hits", "backoffs", "backoff_reasons"} <= set(c)
        assert set(c["by_street"]) <= {"0", "1", "2", "3"}


def test_tournament_eval_counts_pass_new_reasons_through():
    """referee/e3/tournament_eval._counts sums backoff_reasons as a plain dict, so new reasons need no referee change."""
    from referee.e3.tournament_eval import _counts

    class Fake:
        def counts(self):
            return {"decisions": 3, "policy_hits": 1, "backoffs": 2,
                    "backoff_reasons": {"arity_mismatch": 1, "no_key": 1}}

    out = _counts([Fake(), Fake()])
    assert out["backoff_reasons"] == {"arity_mismatch": 2, "no_key": 2}


def test_policy_agents_sum_tolerates_counts_without_by_street():
    """#961 compat: counts from an agent that predates `by_street` still sum."""
    from stalker.tools.icm_calibration import PolicyAgents

    class Old:
        def counts(self):
            return {"decisions": 2, "policy_hits": 1, "backoffs": 1, "backoff_reasons": {"no_key": 1}}

    pa = PolicyAgents.__new__(PolicyAgents)
    pa.agents = [Old()]
    c = pa.counts()
    assert c["decisions"] == 2 and c["by_street"] == {} and c["backoff_rate"] == 0.5


def test_by_street_backoff_reasons_sum_to_totals_and_to_misses():
    """#990: per-street reasons sum to the total reasons; decisions - policy_hits = that street's reason sum."""
    _, agents = play(EMPTY)
    for a in agents:
        c = a.counts()
        tot: dict[str, int] = {}
        for cell in c["by_street"].values():
            assert cell["decisions"] - cell["policy_hits"] == sum(cell["backoff_reasons"].values())
            for r, n in cell["backoff_reasons"].items():
                tot[r] = tot.get(r, 0) + n
        assert tot == c["backoff_reasons"]


def test_missing_keys_top_n_is_exact_and_deterministic():
    """#990: with one key in the table, every other mirrored key is `no_key`; the top list counts them exactly."""
    _, agents = play(EMPTY, cls=Recorder)
    key, m = next((k, m) for a in agents for k, m in a.keys)
    one = PolicyTable({key: [1.0 / m] * m}, k=5, depth="basic", menu="v1", raise_cap=3)
    _, ag = play(one)
    seen: dict[str, int] = {}
    for a in ag:
        for st, lst in a.counts()["missing_keys"].items():
            for e in lst:
                assert e["parts"] == e["key"].split("|") and e["key"] != key
                seen[e["key"]] = seen.get(e["key"], 0) + e["n"]
    assert seen
    for a in ag:
        for st, lst in a.counts()["missing_keys"].items():
            order = [(-e["n"], e["key"]) for e in lst]
            assert order == sorted(order) and len(lst) <= 20
        assert sum(sum(m.values()) for m in a.missing_counts().values()) == a.counts()["backoff_reasons"].get("no_key", 0)


def test_top_missing_synthetic():
    from stalker.agents.e3_policy import top_missing

    out = top_missing({"0": {"b|n4|x": 3, "b|n4|a": 3, "b|n4|z": 1}}, n=2)
    assert out == {"0": [{"key": "b|n4|a", "n": 3, "parts": ["b", "n4", "a"]},
                         {"key": "b|n4|x", "n": 3, "parts": ["b", "n4", "x"]}]}


def test_policy_agents_sum_missing_keys_and_tolerate_old_counts():
    from stalker.tools.icm_calibration import PolicyAgents

    class New:
        def counts(self):
            return {"decisions": 2, "policy_hits": 0, "backoffs": 2, "backoff_reasons": {"no_key": 2},
                    "by_street": {"0": {"decisions": 2, "policy_hits": 0, "backoff_reasons": {"no_key": 2}}}}

        def missing_counts(self):
            return {"0": {"k1": 1, "k2": 1}}

    class Old:
        def counts(self):
            return {"decisions": 1, "policy_hits": 1, "backoffs": 0, "backoff_reasons": {},
                    "by_street": {"0": {"decisions": 1, "policy_hits": 1}}}

    pa = PolicyAgents.__new__(PolicyAgents)
    pa.agents = [New(), New(), Old()]
    c = pa.counts()
    assert c["missing_keys"] == {"0": [{"key": "k1", "n": 2, "parts": ["k1"]}, {"key": "k2", "n": 2, "parts": ["k2"]}]}
    assert c["by_street"]["0"]["backoff_reasons"] == {"no_key": 4}
    json.dumps(c)   # tournament_ab serializes arm.counts() as is



def test_by_players_sums_to_totals():
    """#1010: per-player-count cells sum to the totals, like `by_street`."""
    _, agents = play(EMPTY)
    for a in agents:
        c = a.counts()
        cells = c["by_players"]
        assert sum(v["decisions"] for v in cells.values()) == c["decisions"]
        assert sum(v["policy_hits"] for v in cells.values()) == c["policy_hits"]
        tot: dict[str, int] = {}
        for k, cell in cells.items():
            assert k == "unknown" or 2 <= int(k) <= 9
            for r, n in cell["backoff_reasons"].items():
                tot[r] = tot.get(r, 0) + n
        assert tot == c["backoff_reasons"]


def test_by_players_splits_bubble_from_heads_up():
    """#1010: a 4-handed bubble start played to heads-up fills "4" and "2"; a table with only n4 keys hits in "4"
    and never in "2" (a heads-up hand has no n4 key)."""
    _, rec = play(EMPTY, cls=Recorder)
    keys = {k: m for a in rec for k, m in a.keys if k.split("|")[1:2] == ["n4"]}
    assert keys
    n4 = PolicyTable({k: [1.0 / m] * m for k, m in keys.items()}, k=5, depth="basic", menu="v1", raise_cap=3)
    _, agents = play(n4)
    tot: dict[str, dict] = {}
    for a in agents:
        for k, cell in a.counts()["by_players"].items():
            t = tot.setdefault(k, {"decisions": 0, "policy_hits": 0})
            t["decisions"] += cell["decisions"]
            t["policy_hits"] += cell["policy_hits"]
    assert tot["4"]["decisions"] > 0 and tot["2"]["decisions"] > 0
    assert tot["4"]["policy_hits"] > 0
    assert tot["2"]["policy_hits"] == 0


def test_by_players_unknown_without_new_hand():
    """No NEW_HAND seen for the hand: the decision goes to the "unknown" cell (and backs off as `no_new_hand`)."""
    a = E3PolicyAgent(EMPTY, np.random.default_rng(0))

    class Obs:
        game_id, hand_id = "g", 1

    assert a._hand_players(Obs()) == "unknown"


def test_policy_agents_sum_by_players_and_tolerate_old_counts():
    from stalker.tools.icm_calibration import PolicyAgents

    class New:
        def counts(self):
            return {"decisions": 3, "policy_hits": 1, "backoffs": 2, "backoff_reasons": {"no_key": 2},
                    "by_players": {"2": {"decisions": 2, "policy_hits": 0, "backoff_reasons": {"no_key": 2}},
                                   "4": {"decisions": 1, "policy_hits": 1, "backoff_reasons": {}}}}

    class Old:
        def counts(self):
            return {"decisions": 1, "policy_hits": 1, "backoffs": 0, "backoff_reasons": {}}

    pa = PolicyAgents.__new__(PolicyAgents)
    pa.agents = [New(), New(), Old()]
    c = pa.counts()
    assert list(c["by_players"]) == ["2", "4"]
    assert c["by_players"]["2"] == {"decisions": 4, "policy_hits": 0, "backoff_reasons": {"no_key": 4}}
    assert c["by_players"]["4"]["policy_hits"] == 2


def test_sorted_cells_orders_numerically_with_unknown_last():
    from stalker.agents.e3_policy import sorted_cells

    cell = {"decisions": 1, "policy_hits": 0, "backoff_reasons": {"b": 1, "a": 1}}
    out = sorted_cells({"unknown": cell, "10": cell, "2": cell})
    assert list(out) == ["2", "10", "unknown"] and list(out["2"]["backoff_reasons"]) == ["a", "b"]
