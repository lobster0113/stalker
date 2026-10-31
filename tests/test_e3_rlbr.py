import hashlib
import json

import pytest

from referee.e3 import rlbr as R


def _never_bets(key, acts):
    """Folds to every bet and never bets: any raise takes the blinds, so the best response gains
    1.5bb in the first seat, 1bb in the small blind and 0.5bb in the big blind (3 seats)."""
    a = "f" if "f" in acts else ("k" if "k" in acts else "c")
    return [1.0 if x == a else 0.0 for x in acts]


def _table(pol, players=3):
    return {"policy": pol, "k": 5, "depth": "full", "players": players, "menu": "v1", "raise_cap": 3}


def _registry(tmp_path, dev, audit):
    p = tmp_path / "seeds.json"
    raw = json.dumps({"version": 1, "dev": dev, "audit": audit}).encode()
    p.write_bytes(raw)
    return p, hashlib.sha256(raw).hexdigest()


def test_an_untrained_attacker_is_the_policy_and_gains_exactly_zero():
    r = R.evaluate(_table(_never_bets), R.Attacker(), 20, seed=1)
    assert r["gain_bb_per_hand"] == 0.0 and r["ci95"] == [0.0, 0.0]


def test_rlbr_finds_the_fold_to_any_bet_leak():
    t = _table(_never_bets)
    att = R.train(t, 1000, seed=1, eps=0.2, min_visits=5)
    assert att.deviations() > 0
    r = R.evaluate(t, att, 60, seed=1)
    assert r["ci95_low"] > 0.5 and r["hands"] == 180


def test_training_is_deterministic_per_seed():
    t = _table(_never_bets)
    a, b, c = (R.train(t, 300, seed=s, min_visits=5) for s in (1, 1, 2))
    assert a.sha256() == b.sha256() != c.sha256()


def test_the_attacker_backs_off_to_the_coarse_key_per_entry():
    att = R.Attacker(min_visits=2)
    att.update([(("fine", "coarse"), R.POL)] * 2, -1.0)
    att.update([(("other", "coarse"), "r")] * 2, 1.0)
    assert att.best(("fine", "coarse"), ["f", "c", "r"]) == "r"
    assert att.best(("fine", "coarse"), ["f", "c"]) == R.POL      # "r" is not legal here
    assert att.best(("unseen",), ["f", "c", "r"]) == R.POL


def test_registered_seeds_are_disjoint_and_pinned():
    reg = R.seed_registry()
    assert len(reg["dev"]) >= 2 and reg["audit"] and not set(reg["dev"]) & set(reg["audit"])
    assert hashlib.sha256(R.SEEDS.read_bytes()).hexdigest() == R.SEEDS_SHA256


def test_an_edited_registry_is_refused(tmp_path):
    p, _ = _registry(tmp_path, [1, 2], [99])
    with pytest.raises(R.SeedError, match="pinned"):
        R.seed_registry(p, pinned="0" * 64)


def test_overlapping_dev_and_audit_seeds_are_refused(tmp_path):
    p, sha = _registry(tmp_path, [1, 2], [2, 99])
    with pytest.raises(R.SeedError, match="both dev and audit"):
        R.seed_registry(p, pinned=sha)


def test_a_dev_run_cannot_use_an_audit_seed():
    reg = R.seed_registry()
    audit = reg["audit"][0]
    with pytest.raises(R.SeedError, match="--audit"):
        R.check_seed(audit, audit=False, reg=reg)
    with pytest.raises(R.SeedError, match="not an audit seed"):
        R.check_seed(reg["dev"][0], audit=True, reg=reg)
    assert R.check_seed(audit, audit=True, reg=reg) == "audit"
    assert R.check_seed(reg["dev"][0], audit=False, reg=reg) == "dev"


def test_run_records_seed_role_and_versions():
    reg = R.seed_registry()
    t = dict(_table(_never_bets), sha256="abc")
    r = R.run(t, reg["dev"][0], 200, 4, min_visits=5, reg=reg)
    assert r["role"] == "dev" and r["seed"] == reg["dev"][0] and r["attacker"] == R.ATTACKER
    assert r["code_sha256"] == hashlib.sha256(R.Path(R.__file__).read_bytes()).hexdigest()
    assert len(r["table_sha256"]) == 64 and r["policy_sha256"] == "abc"
    assert r["wording"] == R.WORDING and "lower bound" in r["wording"]
    assert {"gain_bb_per_hand", "ci95", "ci95_low", "deals", "hands"} <= set(r)


def test_cli_refuses_an_audit_seed_without_audit(capsys):
    audit = R.seed_registry()["audit"][0]
    assert R.main([str(R.HERE.parents[1] / "web" / "app" / "policy" / "beginner-6.json"),
                   "--seeds", str(audit)]) == 2
    assert "--audit" in capsys.readouterr().err
