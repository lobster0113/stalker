"""SIM-f (#148): public PHH hands replayed on both engines must end on the recorded stacks."""
import copy

from referee.gate_r import phh
from stalker.tournament.fast_hand import FastHand
from stalker.tournament.hand import Hand

RECS = phh.load_sample()


def test_sample_size_and_stacks_match_on_both_engines():
    assert len(RECS) >= 1000
    for engine in (Hand, FastHand):
        res = phh.run(RECS, engine)
        print(f"{engine.__name__}: compared {res['compared']}/{res['total']} excluded {res['excluded']}")
        assert res["compared"] >= 1000
        assert res["mismatches"] == [], res["mismatches"][:3]
        assert res["compared"] + sum(res["excluded"].values()) == len(RECS)


def test_a_wrong_record_is_reported_as_mismatch():
    bad = copy.deepcopy(RECS[0])
    bad["finishing_stacks"][0] += 1
    bad["finishing_stacks"][1] -= 1
    assert len(phh.run([bad])["mismatches"]) == 1


def test_exclusion_codes():
    base = copy.deepcopy(RECS[0])
    assert phh.exclusion(base) is None
    for key, value, code in [
        ("variant", "FT", "variant"),
        ("antes", [10, 10, 10, 10, 10, 10], "ante"),
        ("blinds_or_straddles", [50, 100, 200, 0, 0, 0], "straddle_or_blinds"),
        ("min_bet", 50, "min_bet"),
        ("finishing_stacks", [10000.5, 9999.5, 10000, 10000, 10000, 10000], "fractional_chips"),
    ]:
        rec = copy.deepcopy(base)
        rec[key] = value
        assert phh.exclusion(rec) == code


def test_fractional_odd_chip_record_is_excluded_not_compared():
    odd = [r for r in RECS if phh.exclusion(r) == "fractional_chips"]
    assert odd and phh.run(odd)["compared"] == 0


def test_replay_rejects_out_of_turn_action():
    bad = copy.deepcopy(RECS[0])
    first = next(i for i, a in enumerate(bad["actions"]) if a[0] == "p")
    bad["actions"][first] = "p1" + bad["actions"][first][2:]  # UTG is p4, so p1 acting first is wrong
    assert len(phh.run([bad])["mismatches"]) == 1
