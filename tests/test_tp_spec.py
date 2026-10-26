import copy
import json
import re
from pathlib import Path

import pytest

from stalker.tp.spec import SpecError, load, validate

ROOT = Path(__file__).resolve().parent.parent
TP_MD = (ROOT / "docs" / "TP.md").read_text(encoding="utf-8")
DEMO = (ROOT / "web" / "demo" / "index.html").read_text(encoding="utf-8")
TIER_NAMES = {"초보": "beginner", "중수": "mid", "고수": "pro"}


def _section(md: str, start: str, end: str) -> str:
    return md[md.index(start):md.index(end)]


def _doc_item_ids() -> set[str]:
    s3 = _section(TP_MD, "## 3. 판단 항목", "## 4.")
    return set(re.findall(r"^\| `([a-z]+\.[a-z]+)` \|", s3, flags=re.M))


def _doc_tiers() -> dict[str, list[str]]:
    s41 = _section(TP_MD, "### 4.1", "### 4.2")
    out, acc = {}, []
    for name, cell in re.findall(r"^\| (초보|중수|고수) \| ([^|]+) \|", s41, flags=re.M):
        acc = acc + re.findall(r"`([a-z]+\.[a-z]+)`", cell)
        out[TIER_NAMES[name]] = list(acc)
    return out


def test_spec_loads_with_stable_hash():
    a, b = load(), load("0.1")
    assert a.version == "0.1" and a.sha256 == b.sha256 and len(a.sha256) == 64


def test_doc_items_equal_spec_items():
    assert _doc_item_ids() == set(load().item_ids)


def test_doc_tier_lists_match_spec():
    spec = load()
    doc = _doc_tiers()
    assert set(doc) == {"beginner", "mid", "pro"}
    for tier, items in doc.items():
        judged = [i for i in spec.tier_items(tier) if i != "act.choice"]
        assert set(judged) == set(items), tier
        assert "act.choice" in spec.tier_items(tier)


def test_doc_scales_and_tolerances_match_spec():
    spec = load().data["tiers"]
    assert spec["beginner"]["steps"] == [0, 25, 50, 75, 100]
    assert len(spec["mid"]["steps"]) == 11 and "11단계" in TP_MD
    assert spec["pro"]["steps"] == "0-100"
    tol = re.search(r"초보 ±([\d.]+), 중수 ±([\d.]+), 고수 ±([\d.]+)", TP_MD).groups()
    assert [spec[t]["tolerance"] for t in ("beginner", "mid", "pro")] == [float(x) for x in tol]


def test_doc_grading_exclusions_match_spec():
    spec = load()
    assert spec.item("plan.pot")["eligible_for_grading"] is False
    assert set(spec.graded()) == set(spec.item_ids) - {"plan.pot"}


def test_doc_na_opportunity_counts_match_spec():
    s31 = _section(TP_MD, "### 3.1", "### 3.2")
    doc = {i: int(n) for i, n in re.findall(r"^\| `(opp\.[a-z]+)` \|.*?기회 < (\d+)회", s31, flags=re.M)}
    spec = load()
    assert doc == {i: spec.item(i)["na"]["min_opportunities"] for i in doc}
    assert set(doc) == {"opp.loose", "opp.aggr", "opp.foldy"}


def test_doc_buckets_match_spec():
    b = load().data["buckets"]
    assert "≤5·5–10·10–15·15–25·25–40·40–60·60–100·100+ BB" in TP_MD
    assert b["effective_stack_bb"] == [5, 10, 15, 25, 40, 60, 100]
    assert b["bet_size_pot_pct"] == [33, 60, 85, 120]
    assert b["preflop_raise_bb"] == [2.5, 3.5, 5]
    s = load().data["size_buckets"]
    assert s["preflop_x"] == [2.2, 2.5, 3.0, "all_in"]
    assert s["postflop_pot_pct"] == [33, 50, 75, 100, 150, "all_in"]


def test_decision_context_fields_are_listed_in_doc():
    s11 = _section(TP_MD, "### 1.1", "### 1.2")
    spec = load().data
    assert spec["decision_context_version"] == "0.1" and "DecisionContext v0.1" in s11
    # Spot-check the facts that most often get confused with judgments.
    for word in ("SPR", "필요 에퀴티", "유효 스택", "합법 액션"):
        assert word in s11
    assert {"spr", "required_equity", "effective_stack_bb", "legal_actions"} <= set(spec["decision_context"])


def _bad(mutate):
    data = copy.deepcopy(load().data)
    mutate(data)
    return data


@pytest.mark.parametrize("mutate,msg", [
    (lambda d: d.pop("tiers"), "missing top-level key 'tiers'"),
    (lambda d: d["items"].append(dict(d["items"][0])), "duplicate item ids"),
    (lambda d: d["items"][0].update(kind="guess"), "kind 'guess'"),
    (lambda d: d["tiers"]["mid"]["items"].remove("opp.range"), "higher tiers must include"),
    (lambda d: d["tiers"]["pro"]["items"].append("opp.bluff"), "unknown items"),
    (lambda d: d["buckets"].update(effective_stack_bb=[10, 5]), "strictly increasing"),
    (lambda d: next(i for i in d["items"] if i["id"] == "plan.pot").update(eligible_for_grading=True),
     "eligible_for_grading to false"),
])
def test_invalid_spec_errors_say_how_to_fix(mutate, msg):
    with pytest.raises(SpecError, match=re.escape(msg)):
        validate(_bad(mutate))


def test_unknown_version_lists_available():
    with pytest.raises(SpecError, match="available: tp_v0_1.json"):
        load("9.9")


def _demo_defs():
    tp_block = DEMO[DEMO.index("const TP = {"):DEMO.index("};", DEMO.index("const TP = {"))]
    items = set(re.findall(r'^\s*"([a-z]+\.[a-z]+)":', tp_block, flags=re.M))
    tiers = {}
    for key, body in re.findall(r"^\s*(beginner|mid|pro): \{(.*?)\},?$", DEMO, flags=re.M):
        tiers[key] = set(re.findall(r'"([a-z]+\.[a-z]+)"', body.split("items:")[1]))
    return items, tiers


def demo_differences() -> list[str]:
    spec = load()
    items, tiers = _demo_defs()
    diffs = []
    if items != set(spec.item_ids):
        diffs.append(f"TP items: demo-only {sorted(items - set(spec.item_ids))}, "
                     f"spec-only {sorted(set(spec.item_ids) - items)}")
    for t in ("beginner", "mid", "pro"):
        want = set(spec.tier_items(t))
        if tiers.get(t) != want:
            got = tiers.get(t, set())
            diffs.append(f"tier {t}: demo-only {sorted(got - want)}, spec-only {sorted(want - got)}")
    return diffs


def test_demo_parser_finds_definitions():
    items, tiers = _demo_defs()
    assert "hand.equity" in items and set(tiers) == {"beginner", "mid", "pro"}


@pytest.mark.xfail(strict=True, reason="demo still on TP v0; #115 updates it, then this must pass")
def test_demo_matches_spec():
    diffs = demo_differences()
    print("\n".join(diffs))
    assert not diffs
