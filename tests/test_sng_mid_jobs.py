"""#957: the SNG in-the-money (stage m, r = 3 and 2) training jobs of ADR 0027 decision 2 step 2."""
import json

import numpy as np
import pytest

from stalker.e3 import game as G
from tests.test_c1_s4_long_job import _spec, _train_flags
from tests.test_cloud_launcher import L, ROOT
from tests.test_e3_icm_payoff import _allin_hand
from tests.test_sng_bubble_job import _argv, _parse

PRESET = "9max_sng_503020"
BUBBLE = "jobs/e3-tp-mid-c1-sng-bubble-pod32.yaml"
JOBS = {3: "jobs/e3-tp-mid-c1-sng-mid3-pod32.yaml", 2: "jobs/e3-tp-mid-c1-sng-mid2-pod32.yaml"}
# the only flags allowed to differ from the bubble job (issue #957); --lbr-hands is E3_BY_PLAYERS_LBR_HANDS_BY_N
CHANGED = {"--players", "--stage", "--out", "--minutes", "--max-iters", "--lbr-hands"}


@pytest.mark.parametrize("players", sorted(JOBS))
def test_flags_differ_from_the_bubble_job_only_where_allowed(players):
    spec, bubble = _spec(JOBS[players]), _spec(BUBBLE)
    f, b = _train_flags(spec.command), _train_flags(bubble.command)
    assert {k: v for k, v in f.items() if k not in CHANGED} == {k: v for k, v in b.items() if k not in CHANGED}
    assert (f["--players"], f["--stage"], f["--lam"], f["--payoff"], f["--preset"], f["--level-index"]) == (
        str(players), "m", "0", "icm", PRESET, "0")
    assert (f["--stacks"], f["--seed"], f["--key-variant"]) == ("bubble:skewed", "1", "c1")
    assert "--prior-result" not in f
    name = f"e3-tp-mid-c1-sng-mid{players}-pod32"
    assert spec.name == name and f["--out"] == spec.result_path == f"/result/{name}.json"
    mine = spec.command.replace(name, "X").replace(f"--lbr-hands {f['--lbr-hands']}", "--lbr-hands L")
    theirs = (bubble.command.replace("e3-tp-mid-c1-sng-bubble-pod32", "X").replace("--lbr-hands 600", "--lbr-hands L")
              .replace("--players 4", f"--players {players}").replace("--stage b", "--stage m"))
    assert mine == theirs, "the pod command around the flags must stay the bubble job's"


@pytest.mark.parametrize("players", sorted(JOBS))
def test_flags_parse_with_pod_train(players):
    a = _parse(_argv(_train_flags(_spec(JOBS[players]).command)))
    from stalker.train_jobs import E3_BY_PLAYERS_LBR_HANDS_BY_N
    assert (a.players, a.stage, a.lam, a.payoff, a.lbr_hands) == (players, "m", 0.0, "icm",
                                                                    E3_BY_PLAYERS_LBR_HANDS_BY_N[players])


@pytest.mark.parametrize("players", sorted(JOBS))
def test_worst_case_cost_and_slow_host_median(players):
    job = L.load_spec(ROOT / JOBS[players])
    assert job.hourly_usd * job.max_minutes / 60 <= 3.60
    (_, _, median), = job.flavors
    assert median > 0, "median_iters_per_s missing: slow-host replacement stays off (#941)"


@pytest.mark.parametrize("players", sorted(JOBS))
def test_tournament_env_is_stage_m_with_valid_stacks(players):
    from stalker.e3.tournament_stacks import sample_tournament_stacks
    from stalker.tools import pod_train as P

    kw, env = P.tournament_env(PRESET, players=players, stage="m", lam=0.0, stacks="bubble:skewed")
    assert (env["stage"], env["lam"], env["stacks"]) == ("m", 0.0, "bubble:skewed")
    assert (kw["stack_preset"], kw["stack_remaining"], kw["stage"]) == (PRESET, players, "m")
    rng = np.random.default_rng(0)
    for _ in range(50):   # the training table asks for at least 2BB (game.deal refuses shorter stacks)
        s = sample_tournament_stacks(rng, PRESET, players, 0, "skewed", min_chips=2 * G.BB)
        assert len(s) == players and all(isinstance(c, int) and c >= 2 * G.BB for c in s)


def _payouts():
    from stalker.tournament.config import load_preset
    return load_preset(PRESET).payout_ratios()


def test_heads_up_icm_is_chip_ev_up_to_scale():
    # 50/30/20 with two left: E = 0.3 + 0.2 * share, so the reward is 0.2 * chips / table chips (same strategy as chip)
    from stalker.e3.icm_payoff import tournament_payoff

    p = _payouts()
    assert p == pytest.approx((0.5, 0.3, 0.2))
    stacks = [8434, 18566]   # a bubble:skewed r=2 draw
    total = sum(stacks)
    fold = G.apply(G.deal(np.random.default_rng(1), n=2, stacks=tuple(stacks)), "f")
    bust = _allin_hand(stacks, shover=1, callers={0}, winner=1)
    for s in (fold, bust):
        assert tournament_payoff(s, stacks, p) == pytest.approx((p[0] - p[1]) * G.payoff(s) / total, abs=1e-12)


def test_three_left_icm_is_not_chip_proportional():
    from stalker.e3.icm_payoff import tournament_payoff

    stacks = [10000, 9000, 8000]
    bust = _allin_hand(stacks, shover=2, callers={0}, winner=0)   # seat 2 busts in 3rd
    r, chips = tournament_payoff(bust, stacks, _payouts()), G.payoff(bust)
    assert chips[1] <= 0 < r[1], "a folded seat gains prize equity when another busts: ICM, not chip share"
    assert r[0] / chips[0] != pytest.approx(r[2] / chips[2])


def _small_argv(f, out):
    small = {**f, "--workers": "1", "--max-iters": "2", "--batch": "1", "--minutes": "5", "--lbr-hands": "4",
             "--out": str(out)}
    for k in ("--sha-file", "--resume-result"):
        small.pop(k, None)
    return _argv(small)


@pytest.mark.slow
@pytest.mark.parametrize("players", sorted(JOBS))
def test_small_run_writes_a_tm0_result(players, tmp_path):
    from stalker.tools import pod_train as P

    out = tmp_path / "r.json"
    assert P.main(_small_argv(_train_flags(_spec(JOBS[players]).command), out)) == 0
    r = json.loads(out.read_text(encoding="utf-8"))
    assert (r["players"], r["iters"]) == (players, 2)
    env = r["model"]["train_env"]
    assert (env["stage"], env["lam"], env["stacks"]) == ("m", 0.0, "bubble:skewed")
    policy = next(p for p in P.unpack(out, tmp_path / "u") if p.name.endswith(".policy.json"))
    keys = [k for k in json.loads(policy.read_text(encoding="utf-8"))["average"] if not k.startswith("call|")]
    assert keys, "the small run learned no keys"
    assert {k.split("|")[1] for k in keys} == {f"n{players}"}
    assert {k.split("|")[8] for k in keys} == {"tm0"}, "every key must carry the in-the-money slot tm0"
