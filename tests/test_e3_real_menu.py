"""E3 "real" size menu (#382): real-play sizes per spot, preflop cap, postflop raise wars, translation."""
import numpy as np
import pytest

from referee.gate_r.e3_suite import run_e3_suite
from stalker import train_jobs as T
from stalker.e3 import game as G
from stalker.e3 import personas
from stalker.e3 import tp_key as K
from stalker.e3 import translate as X

OPENS = ["r2", "r22", "r", "r3", "r35", "r4", "r5", "r6", "r8", "r10"]
RAISES = ["r25", "r", "r4", "r5", "r7", "r10"]
THREE_BETS = ["r25", "r", "r35", "r4", "r5"]
FOUR_BETS = ["r2", "r22", "r25", "r"]


def play(s: G.State, *acts: str) -> G.State:
    for a in acts:
        assert a in G.legal(s), (a, G.legal(s), s.history)
        s = G.apply(s, a)
    return s


def sizes(s: G.State) -> dict[str, int]:
    return {a: G._amount_to(s, a) for a in G.legal(s) if a not in ("f", "c", "k")}


def real(n: int, cap=None) -> G.State:
    return G.deal(np.random.default_rng(0), n, "real", cap)


def test_real_is_a_known_menu():
    assert "real" in G.MENUS


def test_real_preflop_opens():
    s = real(6)
    assert G.legal(s) == ["f", "c", *OPENS, "a"]
    assert sizes(s) == {"r2": 200, "r22": 220, "r": 250, "r3": 300, "r35": 350, "r4": 400, "r5": 500,
                        "r6": 600, "r8": 800, "r10": 1000, "a": G.STACK}


def test_real_isolation_is_each_open_plus_1bb_per_limper():
    s = play(real(6), "c")                     # UTG limps
    assert G.legal(s) == ["f", "c", *OPENS, "a"]
    assert [sizes(s)[a] for a in OPENS] == [300, 320, 350, 400, 450, 500, 600, 700, 900, 1100]
    s = play(s, "c")                           # two limpers
    assert sizes(s)["r2"] == 400 and sizes(s)["r10"] == 1200
    hu = play(real(2), "c")                    # heads-up: the SB completing is a limp
    assert G.legal(hu) == ["c", *OPENS, "a"] and sizes(hu)["r"] == 350


def test_real_preflop_3bets_and_4bets_have_their_own_tables():
    s = play(real(6), "r")                     # UTG opens to 2.5BB
    assert G.legal(s) == ["f", "c", *THREE_BETS, "a"]
    assert sizes(s) == {"r25": 625, "r": 750, "r35": 875, "r4": 1000, "r5": 1250, "a": G.STACK}
    s = play(s, "r")                           # HJ 3-bets to 7.5BB; CO faces it: min raise 1250
    assert G.legal(s) == ["f", "c", *FOUR_BETS, "a"]
    assert sizes(s) == {"r2": 1500, "r22": 1650, "r25": 1875, "r": 2250, "a": G.STACK}
    s = play(real(6), "r10", "r25")            # 10BB open, 25BB 3-bet: 2x = 50BB is above the 40BB min raise
    assert sizes(s)["r2"] == 5000 and "r" in G.legal(s)


def test_real_postflop_raises_are_2_5_to_10x_the_bet():
    s = play(real(2), "c", "c", "b20")         # postflop: pot 200, a 1BB bet
    assert sizes(s) == {"r25": 250, "r": 300, "r4": 400, "r5": 500, "r7": 700, "r10": 1000, "a": G.STACK - 100}


def test_real_postflop_bets_20_to_300_pct():
    s = play(real(2), "c", "c")                # pot 200: 20/33/50% all round up to the 1BB minimum
    assert G.legal(s) == ["k", "b20", "b75", "b100", "b150", "b200", "b300", "a"]
    s = play(real(2), "r3", "c")               # pot 600: every size distinct
    assert G.legal(s) == ["k", "b20", "b33", "b50", "b75", "b100", "b150", "b200", "b300", "a"]
    assert sizes(s) == {"b20": 120, "b33": 198, "b50": 300, "b75": 450, "b100": 600, "b150": 900,
                        "b200": 1200, "b300": 1800, "a": G.STACK - 300}


@pytest.mark.parametrize("cap", [None, 3, 4])
def test_real_preflop_keeps_sized_4bets_then_all_in_only(cap):
    # Owner rule (#382): preflop 2-, 3-, 4-bets have sizes, a 5-bet is all in, whatever the postflop cap.
    s = play(real(6, cap), "r", "r25", "r25")  # open, 3-bet, 4-bet
    assert G.legal(s) == ["f", "c", "a"]


def test_real_postflop_raise_wars_follow_the_cap():
    def flop(cap):
        return play(real(2, cap), "r", "c")    # pot 500
    free = play(flop(None), "b20", "r25", "r25", "r25")   # bet 100, raises to 250, 625, 1562
    assert "r25" in G.legal(free)              # a sized 4th raise
    assert all(t < G.ALLIN_MERGE * G.STACK for a, t in sizes(free).items() if a != "a")
    capped = play(flop(3), "b20", "r25", "r25")   # postflop the bet counts toward the cap
    assert G.legal(capped) == ["f", "c", "a"]


def test_real_labels_are_aggressive_and_personas_find_a_raise():
    for label in {*OPENS, *RAISES, "b20", "b33", "b50", "b75", "b100", "b150", "b200", "b300"}:
        assert label in K.AGGRESSIVE
    tag = personas.Persona("tag")
    s = real(6)
    # AA is the top hand: a "raise" weight must land on a raise label.
    s = s._replace(hole=((48, 49),) + s.hole[1:])
    probs = tag(s)
    acts = G.legal(s)
    assert sum(p for a, p in zip(acts, probs) if a in K.AGGRESSIVE) == pytest.approx(1.0)


def test_real_rule_invariants():
    for cap in (None, 3):
        for n in (2, 6, 9):
            rng = np.random.default_rng([382, n])
            for _ in range(40):
                s = G.deal(rng, n, "real", cap)
                while not s.done:
                    acts = G.legal(s)
                    assert len(acts) == len(set(acts))
                    p, a = s.to_act, acts[int(rng.integers(len(acts)))]
                    if a not in ("f", "c", "k"):
                        to, room = G._amount_to(s, a), s.stack[p] + s.bet[p]
                        assert to == room or to >= max(s.bet) + s.last_raise, (a, to, s.history)
                    s = G.apply(s, a)
                    assert all(s.stack[i] + s.total[i] == G.STACK for i in range(n))
                assert int(G.payoff(s).sum()) == 0


@pytest.mark.slow
@pytest.mark.parametrize("cap", [None, 3])
def test_real_gate_r_pokerkit_replay(cap):
    # The Gate R E3 replay (PokerKit, chip for chip) dealt under the real menu (see tests/test_e3_menu.py).
    with G.rules("real", cap):
        t = run_e3_suite(150, seats=(2, 6, 9), seed=382)
    assert t.passed == t.total, t.failures[:3]


def test_real_job_is_registered_and_resumable():
    kw = T.JOBS["e3-tp-mid-real-w4"].keywords
    assert (kw["tier"], kw["workers"], kw["menu"], kw["raise_cap"]) == ("mid", 4, "real", None)
    assert "e3-tp-mid-real-w4" in T.RESUMABLE


# --- translation (TP.md section 6) --------------------------------------------------------------

def phm(a: float, b: float, x: float) -> float:
    return (b - x) * (1 + a) / ((b - a) * (1 + x))


def test_exact_size_maps_to_itself():
    s = real(6)
    for a, to in sizes(s).items():
        assert X.split(s, to) == [(a, 1.0)]


def test_between_sizes_splits_pseudo_harmonically():
    s = real(6)                                # UTG: top bet 100, call 100, pot 150 -> x = (to - 100) / 250
    out = X.split(s, 450)                      # between r4 (400) and r5 (500)
    f = phm(1.2, 1.6, 1.4)
    assert [a for a, _ in out] == ["r4", "r5"]
    assert out[0][1] == pytest.approx(f) and out[1][1] == pytest.approx(1 - f)


def test_10x_raise_never_maps_to_3x():
    s = play(real(2), "r", "c", "b50")         # flop, pot 500, facing a 250 bet
    assert X.split(s, 2500) == [("r10", 1.0)]
    assert {a for a, _ in X.split(s, 2250)} == {"r7", "r10"}
    for to in range(1750, G.STACK - 250 + 1, 250):
        assert "r" not in {a for a, _ in X.split(s, to)}


def test_all_in_stays_all_in_and_below_smallest_maps_to_it():
    s = play(real(6), "r")
    assert X.split(s, G.STACK) == [("a", 1.0)]
    assert {a for a, _ in X.split(s, 5000)} == {"r5", "a"}
    assert X.split(s, 500) == [("r25", 1.0)]    # min raise, below 2.5x
    capped = play(real(6), "r", "r25", "r25")    # only all in is left as a raise
    assert X.split(capped, 4000) == [("a", 1.0)]


def test_sample_is_seeded_and_follows_the_split():
    s = real(6)
    draw = lambda seed: [X.sample(s, 450, np.random.default_rng(seed)) for _ in range(1)]
    assert draw(5) == draw(5)
    rng = np.random.default_rng(1)
    hits = sum(X.sample(s, 450, rng) == "r4" for _ in range(4000))
    f = phm(1.2, 1.6, 1.4)
    assert abs(hits / 4000 - f) < 4 * (f * (1 - f) / 4000) ** 0.5


def test_illegal_sizes_are_refused():
    s = real(6)
    with pytest.raises(ValueError, match="min"):
        X.split(s, 150)
    with pytest.raises(ValueError, match="all in"):
        X.split(s, G.STACK + 1)


def test_real_avgrange_job_is_arm_b_of_the_real_menu_comparison():
    # #446: the real-menu job with average-strategy ranges; both arms carry the preflop probe
    a, b = T.JOBS["e3-tp-mid-real-w4"].keywords, T.JOBS["e3-tp-mid-real-avgrange-w4"].keywords
    assert {k: v for k, v in b.items() if k not in ("name", "ranges")} == {k: v for k, v in a.items() if k != "name"}
    assert b["ranges"] == "average" and a.get("ranges", "current") == "current" and a["probe"] and b["probe"]
    assert "e3-tp-mid-real-avgrange-w4" in T.RESUMABLE


def test_probe_on_the_average_policy_reaches_the_summary(tmp_path, monkeypatch):
    import json
    from functools import partial

    import referee.e3.lbr as lbr3

    monkeypatch.setattr(lbr3, "exploitability_lb", lambda pol, hands, seed, k, n, depth, extra_sizes=False:
                        {"lbr_bb": 1.0, "hands": hands})
    monkeypatch.setattr(T, "E3_FIELD_HANDS", 2)
    monkeypatch.setattr(T, "E3_PROBE_DEALS", 4)
    monkeypatch.setattr(T, "E3_PROBE_GROUPS", ("AA",))
    job = "e3-tp-real-avgrange-probe-test"
    monkeypatch.setitem(T.JOBS, job, partial(T._e3_tp, tier="beginner", name=job, menu="real", raise_cap=None,
                                             ranges="average", probe=True))
    T.run(job, 2, 1, tmp_path)
    r = json.loads((tmp_path / f"{job}-seed1.json").read_text(encoding="utf-8"))
    p = r["probe_average"]
    assert p["probe"] == "e3_preflop_v1" and p["spot"] == "first_in" and p["deals_per_cell"] == 4
    assert [c["seat"] for c in p["cells"]] == ["UTG", "HJ", "CO", "BTN", "SB"]
    # UTG is always first in; later seats of an untrained policy may not be reached (gain is then None)
    assert p["cells"][0]["deals"] == 4 and p["cells"][0]["best"] and len(p["cells"][0]["gain_ci"]) == 2
    assert all(c["group"] == "AA" and (c["best"] is None) == (c["gain_bb"] is None) for c in p["cells"])
    s = json.loads(T.summary_text(job, tmp_path))
    assert s["probe_average_leaks_by_seed"] == [p["leaks"]] and s["probe_average_by_seed"] == [p]


def test_probe_refuses_key_variants(tmp_path):
    with pytest.raises(SystemExit, match="default keys"):
        T._e3_tp(1, 1, tmp_path, tier="beginner", name="x", key_variant="b1", probe=True)


def test_probe_time_stays_out_of_train_seconds(tmp_path, monkeypatch):
    # #446 review: A gained the probe, so its it/s must stay comparable to earlier A runs without it
    import time as real_time
    from types import SimpleNamespace

    import referee.e3.lbr as lbr3

    clock = [0.0]

    def tick():
        clock[0] += 0.001
        return clock[0]

    def slow_probe(m, avg, seed, workers=1):
        clock[0] += 1000.0
        return {"leaks": 0}

    monkeypatch.setattr(T, "time", SimpleNamespace(monotonic=tick, time=real_time.time, sleep=real_time.sleep))
    monkeypatch.setattr(T, "e3_probe", slow_probe)
    monkeypatch.setattr(lbr3, "exploitability_lb", lambda pol, hands, seed, k, n, depth, extra_sizes=False:
                        {"lbr_bb": 1.0, "hands": hands})
    monkeypatch.setattr(T, "E3_FIELD_HANDS", 2)
    r = T._e3_tp(1, 2, tmp_path, tier="beginner", name="x", menu="real", raise_cap=None, probe=True)
    assert r["probe_average"] == {"leaks": 0}
    assert r["train_seconds"] < 1.0 and r["iters_per_s"] > 2.0
