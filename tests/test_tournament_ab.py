"""Tournament A/B evaluation (#907, ADR 0027 decision 4): CI, adoption rule, common random numbers, JSON fields."""
from __future__ import annotations

import json

import numpy as np
import pytest

from stalker.tools import tournament_ab as T

PRESET = "9max_sng_503020"


def test_mean_ci_matches_hand_computation():
    a, b = [1.0, 2.0, 3.0], [0.0, 4.0]
    r = T.mean_ci([a, b])
    se = np.sqrt(np.var(a, ddof=1) / 3 + np.var(b, ddof=1) / 2) / 2
    assert r["mean"] == pytest.approx((2.0 + 2.0) / 2)
    assert r["se"] == pytest.approx(se)
    assert r["ci_low"] == pytest.approx(2.0 - T.Z95 * se) and r["ci_high"] == pytest.approx(2.0 + T.Z95 * se)
    assert r["cells"] == 2


def test_mean_ci_rejects_cells_without_a_standard_error():
    with pytest.raises(ValueError, match="games must be >= 2"):
        T.mean_ci([[1.0]])
    with pytest.raises(ValueError, match="no cells"):
        T.mean_ci([])


@pytest.mark.parametrize("samples,expected", [
    ([[0.10, 0.11, 0.12, 0.09], [0.10, 0.12, 0.08, 0.11]], "B"),   # clearly positive: lower bound > 0
    ([[0.10, -0.12, 0.05, -0.04], [0.02, -0.03, 0.01, 0.0]], "A"),   # straddles 0: lower bound <= 0
    ([[0.0, 0.0, 0.0], [0.0, 0.0]], "A"),                            # exactly 0: tie stays cold
])
def test_adoption_rule_on_synthetic_samples(samples, expected):
    r = T.mean_ci(samples)
    assert T.verdict(r["ci_low"]) == expected
    if expected == "A" and r["se"] == 0:
        assert r["ci_low"] == 0.0


def test_verdict_boundary():
    assert T.verdict(1e-12) == "B"
    assert T.verdict(0.0) == "A" and T.verdict(-0.5) == "A"


def test_bad_arguments_fail_before_any_game(tmp_path):
    with pytest.raises(ValueError, match="games=1"):
        T.run_ab("x", "y", [PRESET], [4], ["even"], games=1)
    with pytest.raises(ValueError, match="profile"):
        T.run_ab("x", "y", [PRESET], [4], ["flat"], games=2)
    with pytest.raises(ValueError, match="field"):
        T.run_ab("x", "y", [PRESET], [4], ["even"], games=2, field="policy:x")
    with pytest.raises(FileNotFoundError):
        T.run_ab(str(tmp_path / "missing.json"), "y", [PRESET], [4], ["even"], games=2)


def _write_policy(path, table, rows=None):
    doc = {"q": 1000, "k": table.k, "depth": table.depth, "menu": "v1", "raise_cap": 3, "key_variant": "c1",
           "policy": {k: [round(x * 1000) for x in (rows(r) if rows else r)] for k, r in table.policy.items()}}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return str(path)


@pytest.fixture(scope="module")
def policies(tmp_path_factory):
    """A: uniform rows for every key an all-backoff r=4 game reached; B: same keys, all mass on the last action."""
    from tests.test_e3_policy_agent import EMPTY, Recorder, play

    keys = {}
    for profile in ("even", "skewed"):
        _, agents = play(EMPTY, 4, cls=Recorder, profile=profile)
        keys.update({k: m for a in agents for k, m in a.keys})
    from stalker.agents.e3_policy import PolicyTable

    table = PolicyTable({k: [1.0 / m] * m for k, m in keys.items()}, k=5, depth="basic", menu="v1", raise_cap=3)
    d = tmp_path_factory.mktemp("ab")
    a = _write_policy(d / "a.json", table)
    b = _write_policy(d / "b.json", table, rows=lambda r: [0.0] * (len(r) - 1) + [1.0])
    return a, b


@pytest.mark.slow
def test_cli_runs_two_r4_cells_and_is_byte_reproducible(tmp_path, policies):
    a, b = policies
    argv = ["--a", a, "--b", b, "--presets", PRESET, "--remaining", "4", "--profiles", "even,skewed",
            "--layouts", "1", "--games", "2", "--sym-games", "1", "--seed", "10001"]
    assert T.main([*argv, "--out", str(tmp_path / "1.json")]) == 0
    assert T.main([*argv, "--out", str(tmp_path / "2.json")]) == 0
    one = (tmp_path / "1.json").read_bytes()
    assert one == (tmp_path / "2.json").read_bytes()
    out = json.loads(one)
    assert out["schema_version"] == T.SCHEMA_VERSION and out["args"]["seed"] == 10001
    assert set(out["agents"]) == {"A", "B"} and all(len(x["sha256"]) == 64 for x in out["agents"].values())
    assert len(out["cells"]) == 2 and out["verdict"] in ("A", "B")
    for c in out["cells"]:
        assert c["games"] == 2 and c["remaining"] == 4 and c["learner"] in c["players"]
        for arm in ("A", "B"):
            e = c["arms"][arm]
            pol = e["policy"]
            assert {"decisions", "policy_hits", "backoffs", "backoff_rate"} <= set(pol)
            assert pol["policy_hits"] + pol["backoffs"] == pol["decisions"]
            sym = e["symmetric"]
            assert sym["games"] == 1 and {"zone", "max_abs_diff_rel", "max_abs_z", "significant"} <= set(sym)
            assert {"decisions", "policy_hits", "backoffs", "backoff_rate"} <= set(sym["policy"])
            assert "missing_keys" not in pol and "missing_keys" not in sym["policy"]   # #1004: totals only
            assert all("backoff_reasons" in v for v in pol["by_street"].values())
    for arm in ("A", "B"):
        s = out["symmetric_summary"][arm]
        assert {"i_bubble_significant", "ii_bubble_mean_rel"} <= set(s)
        assert out["policy"][arm]["decisions"] == sum(c["arms"][arm]["policy"]["decisions"] for c in out["cells"])
    assert out["policy"]["A"]["policy_hits"] > 0
    for arm in ("A", "B"):
        pol = out["policy"][arm]
        assert "missing_keys" in pol and isinstance(pol["missing_keys"], dict)
        assert pol["by_street"] and all("backoff_reasons" in v for v in pol["by_street"].values())
        no_key0 = pol["by_street"].get("0", {}).get("backoff_reasons", {}).get("no_key", 0)
        if no_key0:
            assert pol["missing_keys"]["0"]
    assert one.decode().count('"missing_keys"') == 2   # one per arm total, none per cell (#1004)


@pytest.mark.slow
def test_missing_keys_do_not_grow_with_cell_count(policies):
    """#1004: a 9-cell run with per-cell key lists was 2.02 MB, over ops' 1 MiB; only the 2 arm totals carry them."""
    a, b = policies
    for layouts in (1, 3):
        out = T.run_ab(a, b, [PRESET], [4], ["even", "skewed"], games=2, layouts=layouts, sym_games=1)
        assert len(out["cells"]) == 2 * layouts
        assert json.dumps(out).count('"missing_keys"') == len(T.ARMS)
        assert all("missing_keys" in out["policy"][arm] for arm in T.ARMS)


def test_cell_counts_drop_only_missing_keys():
    class Arm:
        def counts(self):
            return {"decisions": 3, "by_street": {"0": {"backoff_reasons": {"no_key": 1}}}, "missing_keys": {"0": []}}

    assert T._cell_counts(Arm()) == {"decisions": 3, "by_street": {"0": {"backoff_reasons": {"no_key": 1}}}}


@pytest.mark.slow
def test_same_policy_on_both_arms_is_exactly_zero_and_cold(policies):
    a, _ = policies
    out = T.run_ab(a, a, [PRESET], [4], ["even", "skewed"], games=3, sym_games=0)
    assert out["primary"]["mean"] == 0.0 and out["primary"]["ci_low"] == 0.0
    assert all(c["diff_b_minus_a"]["mean"] == 0.0 for c in out["cells"])
    assert out["verdict"] == "A" and out["adopted"] == "cold"
    assert "symmetric_summary" not in out
