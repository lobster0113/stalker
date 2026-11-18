"""#899: pod_train tournament arguments (--payoff icm --preset --stage --level-index --lam --stacks bubble:*) and train_env."""
import json

import pytest

from stalker.e3 import game as G
from stalker.e3.mccfr import E3MCCFR
from stalker.env.spec import from_tournament
from stalker.tools import pod_train as P
from stalker.tournament.config import load_preset

PRESET = "9max_sng_503020"
CLI = ["--tier", "mid", "--players", "4", "--workers", "2", "--minutes", "0.2", "--max-iters", "6", "--batch", "3",
       "--seed", "1", "--menu", "real", "--no-raise-cap", "--ranges", "average", "--avg-rule", "own",
       "--key-variant", "c1", "--payoff", "icm", "--preset", PRESET, "--stage", "b", "--level-index", "0",
       "--lam", "0", "--stacks", "bubble:skewed"]


@pytest.fixture
def small_eval(monkeypatch):
    import stalker.train_jobs as TJ

    monkeypatch.setattr(TJ, "E3_LBR_HANDS", 20)   # the smoke tests check wiring, not LBR precision


def test_ante_defaults_to_the_preset_levels_bb_ante_and_payouts_to_its_prizes():
    kw, env = P.tournament_env(PRESET, 4, "b", 0, 0.0, "bubble:skewed")
    assert kw == {"payoff": "icm", "payouts": PRESET, "lam": 0.0, "ante": 0, "stage": "b",
                  "stack_preset": PRESET, "stack_remaining": 4, "stack_level": 0}   # 503020 has no ante
    assert load_preset(PRESET).payout_ratios() == (0.5, 0.3, 0.2)
    cfg = load_preset("mtt180_bbante")
    i = next(i for i, lv in enumerate(cfg.levels) if lv.ante)
    lv = cfg.levels[i]
    assert P.tournament_env("mtt180_bbante", 4, "f", i)[0]["ante"] == round(lv.ante * G.BB / lv.bb) > 0
    assert P.tournament_env("mtt180_bbante", 4, "f", i, ante=7)[0]["ante"] == 7   # --ante wins


def test_train_env_names_the_preset_env_id_and_the_training_settings():
    _, env = P.tournament_env(PRESET, 4, "b", 1, 0.25, "bubble:even")
    assert env == {"env_id": from_tournament(load_preset(PRESET)).env_id, "stage": "b", "level_index": 1,
                   "lam": 0.25, "stacks": "bubble:even"}


def test_bad_tournament_arguments_are_refused_shortly():
    with pytest.raises(SystemExit, match="level-index"):
        P.tournament_env(PRESET, 4, level_index=99)
    with pytest.raises(SystemExit, match="preset"):
        P.tournament_env("no_such_preset", 4)
    with pytest.raises(SystemExit, match="--preset"):
        P.main(["--stage", "b", "--out", "x.json"])


@pytest.mark.slow
def test_cli_smoke_writes_train_env_and_a_resumable_v11_checkpoint(tmp_path, small_eval):
    out = tmp_path / "r.json"
    assert P.main([*CLI, "--out", str(out)]) == 0
    r = json.loads(out.read_text(encoding="utf-8"))
    want = {"env_id": from_tournament(load_preset(PRESET)).env_id, "stage": "b", "level_index": 0, "lam": 0.0,
            "stacks": "bubble:skewed"}
    assert r["train_env"] == r["model"]["train_env"] == want and r["stopped_by"] == "max_iters"
    P.unpack(out, tmp_path / "out")
    ck = json.loads((tmp_path / "out" / "e3-tp-mid4-c1-pod-seed1.ckpt.json").read_text(encoding="utf-8"))
    assert ck["version"] == 11 and ck["train_env"] == want
    m = E3MCCFR.from_state(ck)   # the checkpoint continues as the same tournament table
    assert (m.payoff, m.stage, m.ante, m.stacks, m.stack_remaining) == ("icm", "b", 0, "bubble:skewed", 4)
    assert m.regret_hash() == r["regret_sha256"]
    assert all(" tb0" in k or "tb0" in k for k in list(m.regret)[:50])   # the stage slot is the trained one
    # a chain continues from it, and refuses another environment
    nxt = tmp_path / "n.json"
    assert P.main([*CLI[:CLI.index("--max-iters")], "--max-iters", "12", *CLI[CLI.index("--batch"):],
                   "--resume-result", str(out), "--out", str(nxt)]) == 0
    assert json.loads(nxt.read_text(encoding="utf-8"))["resumed_from"] == 6
    other = [*CLI[:-1], "bubble:even"]
    with pytest.raises(SystemExit, match="train_env"):
        P.main([*other, "--resume-result", str(out), "--out", str(nxt)])


def test_resume_refuses_a_checkpoint_of_another_train_env(tmp_path):
    ck = tmp_path / "c.json"
    _, env = P.tournament_env(PRESET, 4, "b", 0, 0.0, "bubble:skewed")
    ck.write_text(json.dumps({"version": 5, "train_env": env}), encoding="utf-8")
    argv = [*CLI[:-1], "bubble:even", "--resume", str(ck), "--out", str(tmp_path / "o.json")]
    with pytest.raises(SystemExit, match="train_env"):
        P.main(argv)
    ck.write_text(json.dumps({"version": 5}), encoding="utf-8")   # a cash checkpoint
    with pytest.raises(SystemExit, match="train_env"):
        P.main(argv)


@pytest.mark.slow
def test_workers_two_twice_is_bit_identical_and_bubble_stacks_change_the_training():
    kw, _ = P.tournament_env(PRESET, 4, "b", 0, 0.0, "bubble:skewed")
    base = dict(tier="mid", players=4, minutes=5, seed=1, batch=2, menu="real", raise_cap=None, ranges="average",
                avg_rule="own", key_variant="c1", max_iters=8, log=lambda s: None)

    def hash_of(stacks, env, workers):
        m, _ = P.train(workers=workers, stacks=stacks, env=env, **base)
        return m.regret_hash()

    a, b = hash_of("bubble:skewed", kw, 2), hash_of("bubble:skewed", kw, 2)
    assert a == b                                   # the stack sample reached the workers, deterministically
    uniform = {k: v for k, v in kw.items() if not k.startswith("stack_")}
    assert hash_of("uniform", uniform, 2) != a      # a hand dealt bubble stacks is not a uniform 100BB hand


@pytest.mark.slow
def test_plain_run_has_no_train_env_and_keeps_its_result_keys(small_eval):
    r = P.run("beginner", 3, 1, minutes=0.001, seed=1, batch=1, max_iters=2)
    assert "train_env" not in r and "train_env" not in r["model"] and "payoff" not in r["model"]
    assert P.tournament_args(type("A", (), {"payoff": "chip", "preset": None, "stage": "c", "level_index": 0,
                                            "lam": 0.0, "ante": None, "stacks": "uniform"})) == ({}, None)


def test_chip_payoff_preset_run_resumes_from_its_result_and_checkpoint(tmp_path, small_eval):
    """Review of #908: a chip run with no ante/stage/bubble stacks must keep state()'s version, not 9."""
    base = ["--tier", "mid", "--players", "4", "--workers", "1", "--max-iters", "5", "--batch", "5", "--seed", "1",
            "--menu", "real", "--no-raise-cap", "--key-variant", "c1", "--payoff", "chip", "--preset", PRESET]
    out = tmp_path / "r.json"
    assert P.main([*base, "--out", str(out)]) == 0
    nxt = tmp_path / "n.json"
    assert P.main([*base[:base.index("--max-iters")], "--max-iters", "10", *base[base.index("--batch"):],
                   "--resume-result", str(out), "--out", str(nxt)]) == 0
    assert json.loads(nxt.read_text(encoding="utf-8"))["resumed_from"] == 5
    P.unpack(out, tmp_path / "out")
    ck = next((tmp_path / "out").glob("*.ckpt.json"))
    assert E3MCCFR.from_state(json.loads(ck.read_text(encoding="utf-8"))).payoff == "chip"


@pytest.mark.slow
def test_lbr_hands_flag_sets_the_evaluation_deals(tmp_path, small_eval):
    out = tmp_path / "r.json"
    assert P.main([*CLI, "--lbr-hands", "7", "--out", str(out)]) == 0
    r = json.loads(out.read_text(encoding="utf-8"))
    assert r["lbr"]["hands"] == 7 and r["lbr_average"]["hands"] == 7
