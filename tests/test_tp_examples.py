import json
from collections import Counter

import pytest

from stalker.core.cards import cards
from stalker.tp import reference as R
from stalker.tp.spec import SPEC_DIR, load

EXAMPLES = json.loads((SPEC_DIR / "examples_v0_1.json").read_text(encoding="utf-8"))
CASES = EXAMPLES["cases"]
REQUIRED_ITEMS = ["opp.range", "hand.equity", "board.adv", "hand.outs", "hand.vuln", "opp.value", "plan.foldeq", "plan.icm"]


def _c(s: str) -> tuple:
    return tuple(cards(s)) if s else ()


def _compute(case: dict):
    item, x = case["item"], case["inputs"]
    if item == "hand.equity":
        return R.equity(_c(x["hero"]), _c(x["board"]), [R.parse_range(r) for r in x["ranges"]])
    if item == "opp.range":
        return R.opp_range(_c(x["hero"]), _c(x["board"]), x["policy"])
    if item == "board.adv":
        return {"value": R.board_adv(R.parse_range(x["my_range"]), R.parse_range(x["opp_range"]), _c(x["board"]))}
    if item in ("hand.outs", "hand.vuln"):
        r = R.next_card_shift(_c(x["hero"]), _c(x["board"]), [R.parse_range(r) for r in x["ranges"]])
        return {"value": r["outs" if item == "hand.outs" else "vuln"]}
    if item == "opp.value":
        return {"value": R.opp_value(R.parse_range(x["bet_range"]), R.parse_range(x["my_calling_range"]),
                                     _c(x["board"]))}
    if item == "plan.foldeq":
        return {"value": R.fold_equity([[tuple(e) for e in opp] for opp in x["opponents"]])}
    if item == "plan.icm":
        return {"value": R.icm_risk_premium(**x)["premium_pp"]}
    raise AssertionError(f"no reference for {item}")


def _match(got, want, tol, path=""):
    if isinstance(want, dict):
        for k, v in want.items():
            assert k in got, f"{path}{k} missing"
            _match(got[k], v, tol, f"{path}{k}.")
    else:
        assert got == pytest.approx(want, abs=tol), f"{path.rstrip('.')}: got {got}, want {want}"


VALUE_CASES = [c for c in CASES if "inputs" in c]
NA_CASES = [c for c in CASES if "context" in c]


@pytest.mark.parametrize("case", VALUE_CASES, ids=[c["id"] for c in VALUE_CASES])
def test_reference_reproduces_hand_calculation(case):
    _match(_compute(case), case["expected"], case["tolerance"])


@pytest.mark.parametrize("case", NA_CASES, ids=[c["id"] for c in NA_CASES])
def test_na_conditions(case):
    spec = load()
    mins = {i["id"]: i["na"]["min_opportunities"] for i in spec.data["items"] if i.get("na")}
    reason = R.not_applicable(case["item"], case["context"], mins)
    assert (reason is not None) == case["expected"]["na"], reason


def test_every_graded_item_has_two_cases_and_each_case_is_documented():
    counts = Counter(c["item"] for c in VALUE_CASES)
    assert all(counts[i] >= 2 for i in REQUIRED_ITEMS), counts
    spec = load()
    for c in CASES:
        assert c["item"] in spec.item_ids and c["rationale"]
        assert set(c.get("assumptions", [])) <= set(EXAMPLES["assumptions"])
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))


def test_na_case_for_each_na_condition():
    na_items = {c["item"] for c in NA_CASES if c["expected"]["na"]}
    assert {"hand.outs", "hand.vuln", "opp.value", "board.adv", "plan.foldeq", "plan.icm", "opp.loose",
            "opp.range"} <= na_items


def test_equity_records_win_tie_and_equity_separately():
    split = next(c for c in VALUE_CASES if c["id"] == "equity-board-plays-split")
    got = _compute(split)
    assert set(got) == {"win", "tie", "equity"} and got["equity"] != got["win"] + got["tie"]


def test_examples_track_the_spec_version():
    assert EXAMPLES["tp_version"] == load().version


def test_reference_rejects_impossible_inputs():
    with pytest.raises(ValueError, match="compatible"):
        R.equity(_c("AhAd"), _c("Kc7d2s9h3c"), [R.parse_range([["AhKs", 1]])])
    with pytest.raises(ValueError, match="flop or turn"):
        R.next_card_shift(_c("AhAd"), _c("Kc7d2s9h3c"), [R.parse_range([["KsKd", 1]])])
    with pytest.raises(ValueError, match="cover the call"):
        R.icm_risk_premium([500, 0, 1000], [50, 30, 20], 0, 1, 1000, 1000)
